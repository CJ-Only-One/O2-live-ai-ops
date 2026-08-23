#!/usr/bin/env python3
"""order-worker 의 파드당 처리량을 잰다. KEDA ScaledObject 의 근거값이다.

api 를 거치지 않고 SQS 에 직접 넣는다. `POST /api/orders` 로 던지면 api 의
천장(M-009, 300 RPS)에 먼저 막혀 **워커가 아니라 api 를 재게 된다.**

k6 를 쓰지 않는 이유는 SigV4 서명을 못 하기 때문이다. 그리고 이 워커에는
도착률 제어가 필요 없다 — 큐를 미리 채우고 **비는 데 걸린 시간**을 재면
그것이 곧 처리량이다. 생성기가 병목이 될 여지도 없어진다.

    replicas 0 → N건 적재 → replicas R → 큐가 빌 때까지 시간

**replicas 를 여러 단계로 도는 것이 이 스크립트의 핵심이다.** 파드당 값만
재고 상한을 안 재면, KEDA 가 파드를 늘려서 RDS 를 죽인다. 선형으로 늘면
파드가 병목이고, 어디서 꺾이면 그 지점이 DB 한계이자 maxReplicaCount 다.

사용법:

    loadtest/order-queue.py                        # 10,000건 × replicas 1,2,4
    loadtest/order-queue.py -n 20000 -r 1 2 4 8
    loadtest/order-queue.py --dry-run              # 적재만, 스케일 안 건드림

끝나고 할 일은 마지막에 출력한다. run.sh 와 같다.
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field

DEPLOY = "order-worker"
NS = "o2-dev"

# **`app=` 이 아니다.** 매니페스트가 app.kubernetes.io/name 을 쓴다. 틀리면
# 매칭이 0건인데 kubectl 은 성공으로 끝나서, 파드가 살아 있는 채로 적재가
# 시작되고 top 은 0m 을 찍는다. 표가 나오는데 전부 거짓이 된다.
SELECTOR = f"app.kubernetes.io/name={DEPLOY}"
REGION = "ap-northeast-2"

# 이 표식으로 넣고 이 표식으로 지운다. 실제 방송 데이터와 섞이면 못 가른다.
BROADCAST_ID = "bc_loadtest"

SAMPLE_SEC = 5

# AWS CLI v2 는 터미널에서 출력을 less 로 넘긴다. 중간에 페이저가 뜨면 사람이
# q 를 누를 때까지 멈춘다 (run.sh 와 같은 이유).
os.environ.setdefault("AWS_PAGER", "")


def aws(*args: str) -> dict:
    """boto3 대신 aws CLI 를 쓴다. run.sh 가 이미 쓰고 있어 설치할 것이 없다 —
    Homebrew 파이썬은 PEP 668 로 pip install 을 막는다."""
    out = sh("aws", "sqs", *args, "--region", REGION, "--output", "json")
    return json.loads(out) if out.strip() else {}


def sh(*args: str, stdin: str | None = None) -> str:
    """실패하면 stderr 를 그대로 보여준다.

    capture_output 만 하고 죽으면 CalledProcessError 에 명령줄만 남는다 —
    적재 배치의 명령줄은 수천 자라 **정작 원인은 안 보인다.**
    """
    p = subprocess.run(args, input=stdin, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"{args[0]} {args[1] if len(args) > 1 else ''} 실패"
                           f"(rc={p.returncode}): {p.stderr.strip()[-400:]}")
    return p.stdout


# RDS 는 VPC 안이라 노트북에서 못 붙는다. api 파드에는 pymysql 과 DB 자격증명이
# 이미 들어와 있으므로 거기서 돌린다 — bastion 도, 포트포워딩도 필요 없다.
_SQL = """
import os, pymysql, sys
c = pymysql.connect(host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
                    password=os.environ["DB_PASSWORD"], database=os.environ["DB_NAME"])
cur = c.cursor()
cur.execute("SELECT COUNT(*) FROM orders WHERE broadcast_id = %s", (sys.argv[1],))
print("남은 행:", cur.fetchone()[0])
if len(sys.argv) > 2:
    # 한 번에 다 지우면 트랜잭션이 길어진다. 5,000행씩 끊는다.
    total = 0
    while True:
        n = cur.execute("DELETE FROM orders WHERE broadcast_id = %s LIMIT 5000", (sys.argv[1],))
        c.commit()
        total += n
        if n == 0:
            break
    print("지운 행:", total)
"""


def rows(delete: bool = False) -> tuple[int, str]:
    """표식이 붙은 행만 센다/지운다. 표식은 파라미터로 넘겨 문자열을 조립하지 않는다."""
    argv = ["-", BROADCAST_ID] + (["delete"] if delete else [])
    out = sh("kubectl", "exec", "-i", "-n", NS, "deploy/api", "--", "python", *argv,
             stdin=_SQL).strip()
    return int(out.splitlines()[0].split(":")[1]), out


def queue_url() -> str:
    """워커가 실제로 보는 큐를 쓴다. 손으로 적으면 다른 큐를 재게 된다."""
    cm = json.loads(sh("kubectl", "get", "cm", "o2-data", "-n", NS, "-o", "json"))
    url = cm["data"].get("SQS_ORDER_QUEUE_URL", "")
    if not url:
        sys.exit("ConfigMap o2-data 에 SQS_ORDER_QUEUE_URL 이 없다")
    return url


def make_message(seq: int) -> str:
    """워커의 _parse 가 요구하는 8개 필드를 모두 채운다.

    하나라도 빠지면 PermanentError 로 **즉시 버려져서** 처리량이 실제보다
    몇 배 높게 나온다. 표가 통째로 거짓말이 된다.

    order_id·idem_key 는 건마다 유니크해야 한다. 겹치면 uk_idem 위반으로
    IntegrityError 경로를 타서 INSERT 비용이 안 잡힌다.
    """
    return json.dumps(
        {
            "order_id": f"lt_{uuid.uuid4().hex[:24]}",  # String(32)
            "idem_key": str(uuid.uuid4()),  # CHAR(36)
            "broadcast_id": BROADCAST_ID,
            "sku_id": 1,
            "user_key": f"lt_user_{seq % 1000}",
            "qty": 1,
            "unit_price": 1000,
            "amount": 1000,
        }
    )


def fill(url: str, total: int) -> None:
    """send_message_batch 는 한 번에 10건이 상한이다. 1만 건이면 1,000콜이라
    직렬로 넣으면 적재만 몇 분 걸린다."""
    print(f"적재 {total:,}건 ...", end="", flush=True)

    def put(base: int) -> int:
        entries = [
            {"Id": str(i), "MessageBody": make_message(base + i)}
            for i in range(min(10, total - base))
        ]
        # 동시 적재는 가끔 스로틀에 걸린다. 한 번 튕겼다고 측정 전체를 버리지
        # 않는다 — 적재가 덜 되면 어차피 아래에서 멈춘다.
        for attempt in range(3):
            try:
                resp = aws("send-message-batch", "--queue-url", url,
                           "--entries", json.dumps(entries))
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        failed = len(resp.get("Failed", []))
        if failed:
            print(f"\n  적재 실패 {failed}건: {resp['Failed'][0].get('Message')}")
        return len(entries) - failed

    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        sent = sum(pool.map(put, range(0, total, 10)))
    print(f" {sent:,}건 / {time.time() - started:.0f}초")
    if sent < total:
        sys.exit("적재가 덜 됐다. 이 상태로 재면 표가 틀린다")


def depth(url: str) -> int:
    """Visible 만 보면 처리 중인 것을 0 으로 착각해 조기 종료한다."""
    a = aws("get-queue-attributes", "--queue-url", url, "--attribute-names",
            "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible")["Attributes"]
    return int(a["ApproximateNumberOfMessages"]) + int(a["ApproximateNumberOfMessagesNotVisible"])


def dlq(url: str) -> str | None:
    """DLQ 로 빠진 메시지는 큐에서 사라진다. 그만큼 배수가 빨리 끝나므로
    **처리량이 높게 나온다.** 사람이 나중에 보라고 두면 그냥 안 본다."""
    policy = aws("get-queue-attributes", "--queue-url", url,
                 "--attribute-names", "RedrivePolicy")["Attributes"].get("RedrivePolicy")
    if not policy:
        return None
    name = json.loads(policy)["deadLetterTargetArn"].rsplit(":", 1)[-1]
    return aws("get-queue-url", "--queue-name", name)["QueueUrl"]


ARGO_APP = "o2-dev"


def autosync(policy: dict | None) -> dict | None:
    """측정 동안 Argo CD 자동 동기화를 끈다.

    **끄지 않으면 kubectl scale 이 몇 초 만에 되돌아간다.** selfHeal 이 매니페스트의
    replicas 를 정답으로 보기 때문이다. 파드가 안 죽는 것처럼 보이는데 에러는
    안 난다 — ScaledObject 를 붙일 때 replicas 를 지워야 하는 이유와 같은
    함정이다 (decisions.md D-041 · D-004).

    policy 를 주면 그대로 복원하고, None 을 주면 끄고 원래 값을 돌려준다.
    """
    app = json.loads(sh("kubectl", "get", "app", ARGO_APP, "-n", "argocd", "-o", "json"))
    current = app["spec"].get("syncPolicy", {}).get("automated")
    body = {"spec": {"syncPolicy": {"automated": policy}}}
    sh("kubectl", "patch", "app", ARGO_APP, "-n", "argocd", "--type", "merge",
       "-p", json.dumps(body))
    return current


def scale(replicas: int) -> None:
    sh("kubectl", "scale", f"deploy/{DEPLOY}", "-n", NS, f"--replicas={replicas}")
    if replicas:
        sh("kubectl", "rollout", "status", f"deploy/{DEPLOY}", "-n", NS, "--timeout=180s")
    else:
        # rollout status 는 replicas 0 에서 바로 끝난다. 파드가 실제로 사라질
        # 때까지 기다리지 않으면 적재 중에 이전 파드가 먹기 시작한다.
        for _ in range(60):
            if not sh("kubectl", "get", "pod", "-n", NS, "-l", SELECTOR,
                      "--no-headers", "--ignore-not-found").strip():
                return
            time.sleep(2)
        sys.exit("파드가 안 죽는다. graceful shutdown 이 걸린 것인지 확인해라")


_TOP = re.compile(r"^\S+\s+(\d+)m\s+(\d+)Mi", re.M)


def top_max(prev: tuple[int, int]) -> tuple[int, int]:
    """파드 전체 합의 최댓값. CPU 가 안 오르는데 처리량이 낮으면 앱 내부 문제다
    (run.sh 의 읽는 법과 같다)."""
    try:
        out = sh("kubectl", "top", "pod", "-n", NS, "-l", SELECTOR, "--no-headers")
    except RuntimeError:
        return prev  # metrics-server 가 파드를 아직 모른다 (sh 가 RuntimeError 로 올린다)
    cpu = sum(int(m[0]) for m in _TOP.findall(out))
    mem = sum(int(m[1]) for m in _TOP.findall(out))
    return max(prev[0], cpu), max(prev[1], mem)


@dataclass
class Result:
    replicas: int
    total: int
    wall: float = 0.0
    steady: float = 0.0  # 90% → 10% 구간. 램프업·꼬리를 뺀 값
    cpu: int = 0
    mem: int = 0
    restarts: int = 0
    dead: int = 0
    samples: list = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.total * 0.8 / self.steady if self.steady else 0.0

    @property
    def per_pod(self) -> float:
        return self.rate / self.replicas if self.replicas else 0.0

    @property
    def valid(self) -> bool:
        """폴링보다 빨리 끝나면 값이 아니라 잡음이다.

        100건짜리로 돌리면 첫 폴링 전에 큐가 비어 처리량이 몇 배로 나오고
        CPU 는 0m 이 찍힌다. **그래도 표는 정상으로 보인다.** metrics-server
        해상도가 약 15초라 CPU 도 그만큼은 돌아야 잡힌다.
        """
        return self.steady >= 3 * SAMPLE_SEC and self.cpu > 0


def drain(url: str, dlq_url: str | None, replicas: int, total: int, base: int) -> Result:
    """진행도를 **큐 깊이가 아니라 MySQL 행 수로** 본다.

    ApproximateNumberOfMessages 는 이름대로 근사값인데, 소비 직후 크게 늦는다.
    2026-08-23 에 Visible·NotVisible 이 둘 다 0 을 보고한 뒤 2,325건이 뒤늦게
    나타났다. 그 0 을 완료로 믿으면 배수 시간이 짧게 나와 **처리량이 부풀려진다.**
    행 수는 정확하고 단조증가라 늦을 일이 없다.
    """
    r = Result(replicas=replicas, total=total)
    dead0 = depth(dlq_url) if dlq_url else 0
    hi, lo = total * 0.1, total * 0.9
    t90 = t10 = None
    usage = (0, 0)

    started = time.time()
    while True:
        done = rows()[0] - base
        left = total - done
        now = time.time() - started
        r.samples.append((round(now), left))
        usage = top_max(usage)

        if t90 is None and done >= hi:
            t90 = now
        if t10 is None and done >= lo:
            t10 = now
        if done >= total:
            r.wall = now
            break
        if now > 1800:
            print("  30분을 넘겼다. 배수가 안 되는 것이니 워커 로그를 봐라")
            r.wall = now
            break
        time.sleep(SAMPLE_SEC)

    r.cpu, r.mem = usage
    r.dead = (depth(dlq_url) - dead0) if dlq_url else 0
    r.steady = (t10 - t90) if (t10 is not None and t90 is not None and t10 > t90) else r.wall
    pods = sh("kubectl", "get", "pod", "-n", NS, "-l", SELECTOR, "--no-headers")
    r.restarts = sum(int(line.split()[3]) for line in pods.strip().splitlines() if line)
    return r


def self_check() -> None:
    """메시지가 워커의 계약과 맞는지만 본다. AWS 도 클러스터도 안 탄다.

    필드가 하나라도 빠지면 워커가 즉시 버려서 처리량이 몇 배 높게 나오는데,
    **표를 보면 성공처럼 보인다.** 그 조용한 실패를 여기서 잡는다.
    필수 필드 목록은 워커 소스에서 직접 읽는다 — 여기 베껴 두면 낡는다.
    """
    src = open("apps/order-worker/worker/main.py", encoding="utf-8").read()
    required = re.search(r"required = \(([^)]*)\)", src).group(1)
    required = re.findall(r'"([^"]+)"', required)
    assert len(required) == 8, required

    msg = json.loads(make_message(0))
    missing = [k for k in required if msg.get(k) is None]
    assert not missing, f"워커가 요구하는 필드 누락: {missing}"

    assert len(msg["order_id"]) <= 32, msg["order_id"]  # String(32)
    assert len(msg["idem_key"]) == 36, msg["idem_key"]  # CHAR(36)
    ids = {json.loads(make_message(i))["idem_key"] for i in range(100)}
    assert len(ids) == 100, "idem_key 가 겹친다. uk_idem 위반으로 INSERT 가 안 잡힌다"

    r = Result(replicas=2, total=1000, steady=10.0)
    assert r.rate == 80.0, r.rate  # 1000 x 0.8 / 10
    assert r.per_pod == 40.0, r.per_pod
    print("self-check 통과")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--messages", type=int, default=10000)
    ap.add_argument("-r", "--replicas", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--dry-run", action="store_true", help="적재만 하고 스케일은 안 건드린다")
    ap.add_argument("--self-check", action="store_true", help="메시지 계약만 검사한다")
    ap.add_argument("--count", action="store_true", help=f"{BROADCAST_ID} 행 수만 센다")
    ap.add_argument("--cleanup", action="store_true", help=f"{BROADCAST_ID} 행을 지운다")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return

    if args.count or args.cleanup:
        print(rows(delete=args.cleanup)[1])
        return

    url = queue_url()
    dlq_url = dlq(url)
    print(f"큐: {url}\nDLQ: {dlq_url or '없음'}\n네임스페이스: {NS}\n")

    if args.dry_run:
        fill(url, args.messages)
        return

    origin = int(sh("kubectl", "get", f"deploy/{DEPLOY}", "-n", NS,
                    "-o", "jsonpath={.spec.replicas}") or 1)
    saved = autosync(None)
    print(f"Argo CD 자동 동기화를 껐다 (원래: {saved}). 측정이 끝나면 되돌린다.\n")
    results = []
    try:
        for replicas in args.replicas:
            print(f"=== replicas={replicas} ===")
            scale(0)
            # 앞 단계의 in-flight 가 가시성 타임아웃(60초) 뒤에 되살아난다.
            # 속성값도 늦으므로 넉넉히 기다렸다가 확인한다.
            for _ in range(12):
                left = depth(url)
                if left == 0:
                    break
                print(f"  큐에 {left}건이 남아 있다. 기다린다")
                time.sleep(15)
            else:
                sys.exit("큐가 안 비워진다. 손으로 확인해라")
            base = rows()[0]
            fill(url, args.messages)
            scale(replicas)
            r = drain(url, dlq_url, replicas, args.messages, base)
            results.append(r)
            if not r.valid:
                print(f"  배수 {r.wall:.0f}초 — **너무 빨리 끝나 측정이 안 됐다.** "
                      f"-n 을 늘려라 (최소 {3 * SAMPLE_SEC}초는 돌아야 한다)")
                continue
            print(f"  배수 {r.wall:.0f}초 · 처리량 {r.rate:.1f}/s "
                  f"· 파드당 {r.per_pod:.1f}/s · CPU {r.cpu}m · MEM {r.mem}Mi"
                  + (f" · 재시작 {r.restarts}회" if r.restarts else "")
                  + (f" · DLQ {r.dead}건" if r.dead else ""))
    finally:
        # **하나씩 따로 시도한다.** 앞의 것이 실패해도 뒤의 것은 해야 한다.
        # 2026-08-23 에 노트북 네트워크가 끊겨 scale 이 실패했는데, 같은 블록에
        # 있던 autosync 복원까지 건너뛰어 replicas 16 과 자동 동기화 꺼짐이
        # 5시간 방치됐다. 되돌리기는 최선을 다하고, 못 한 것은 크게 알린다.
        for label, fn in (("replicas 복원", lambda: scale(origin)),
                          ("자동 동기화 복원", lambda: autosync(saved))):
            try:
                fn()
                print(f"{label} 완료")
            except Exception as exc:
                print(f"\n**{label} 실패 — 손으로 되돌려라.** {exc}\n"
                      f"  kubectl scale deploy/{DEPLOY} -n {NS} --replicas={origin}\n"
                      f"  kubectl patch app {ARGO_APP} -n argocd --type merge "
                      f"-p '{json.dumps({'spec': {'syncPolicy': {'automated': saved}}})}'")

    results = [r for r in results if r.valid]
    if not results:
        print("\n쓸 수 있는 값이 없다. -n 을 늘려서 다시 돌려라")
        return

    print("\n| 날짜 | replicas | 배수(초) | 처리량(msg/s) | 파드당 | CPU | MEM |")
    print("|---|---|---|---|---|---|---|")
    today = time.strftime("%Y-%m-%d")
    for r in results:
        print(f"| {today} | {r.replicas} | {r.wall:.0f} | {r.rate:.1f} | "
              f"{r.per_pod:.1f} | {r.cpu}m | {r.mem}Mi |")

    dead = sum(r.dead for r in results)
    if dead:
        print(f"\n**DLQ 로 {dead}건이 빠졌다. 위 표는 무효다.** 그만큼 처리하지 않고 "
              "끝났으므로 처리량이 높게 나온다. 워커 로그에서 원인을 먼저 봐라")

    if len(results) > 1:
        first = results[0].per_pod
        worst = min(r.per_pod for r in results[1:])
        if first and worst < first * 0.7:
            print(f"""
파드당 처리량이 {first:.1f} → {worst:.1f} 로 꺾였다. **범인이 둘이라 여기서는 못
가른다.** 확인하기 전에는 maxReplicaCount 를 정하지 마라.

  노드 CPU   kubectl top nodes — allocatable 에 붙었으면 이쪽이다.
             requests 가 실사용보다 작으면 Karpenter 는 Pending 을 못 봐서
             노드를 사지 않는다. **requests 를 고치고 다시 재야 한다.**
  RDS        CloudWatch AWS/RDS 의 CPUUtilization · WriteIOPS ·
             DatabaseConnections. 여기가 한가하면 DB 는 무죄다.

노드가 범인이면 이 꺾임은 상한이 아니라 requests 오류의 부산물이다.""")

    print(f"""
== 끝나고 할 것 ==

1. 넣은 주문을 지운다. 안 지우면 다음 측정의 INSERT 가 큰 테이블에 들어간다.

   loadtest/order-queue.py --count     # 먼저 세어 보고
   loadtest/order-queue.py --cleanup   # 지운다

2. 평시 기준(baseline)을 지운다. run.sh 의 안내와 같다 — 부하 구간이 EWMA 에
   섞이면 조기 경보가 영영 안 울린다.

3. DLQ 를 본다. 0 이 아니면 위 표는 무효다 (버려진 메시지만큼 빨리 끝난다).

4. queueLength 로 환산해서 measurements.md 에 M-011 로 남긴다.
   ScaledObject 에 들어가는 것은 msg/s 가 아니라 **파드당 목표 큐 길이**다.

       queueLength = 파드당 처리량(msg/s) x 허용 지연(초)

   인덱스 한 줄도 같이 넣는다 (CI 가 막는다).
""")


if __name__ == "__main__":
    main()
