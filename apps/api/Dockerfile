# ── 빌드 단계 ────────────────────────────────────────────────
# 로컬에 JDK/Gradle이 없어도 되도록 Gradle 이미지를 그대로 쓴다.
# wrapper를 추가하면 ./gradlew 로 바꿔도 된다.
FROM gradle:8.14-jdk21-alpine AS build
WORKDIR /workspace

# 빌드 스크립트를 먼저 넣어 의존성 레이어를 소스와 분리한다.
# 소스만 바뀌면 아래 의존성 해석 레이어는 캐시에서 재사용된다.
COPY settings.gradle.kts build.gradle.kts ./
RUN gradle dependencies --no-daemon || true

COPY src src
# 테스트는 CI에서 이미 돌렸다. 여기서 또 돌리면 이미지 빌드만 느려진다.
RUN gradle bootJar --no-daemon -x test && mv build/libs/*.jar /workspace/app.jar

# ── 실행 단계 ────────────────────────────────────────────────
FROM eclipse-temurin:21-jre-alpine AS runtime
WORKDIR /app

# UID를 반드시 숫자로 고정한다. `USER app` 처럼 이름으로 지정하면
# 매니페스트의 runAsNonRoot: true 와 만났을 때 kubelet이 root 여부를
# 검증하지 못해 CreateContainerConfigError 로 컨테이너 생성이 거부된다.
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app

COPY --from=build --chown=10001:10001 /workspace/app.jar app.jar

USER 10001
EXPOSE 8080

# 컨테이너 메모리 제한을 JVM이 인식하게 한다.
# 이게 없으면 JVM이 노드 전체 메모리 기준으로 힙을 잡다가 OOMKilled 당한다.
ENV JAVA_OPTS="-XX:MaxRAMPercentage=70.0"

ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar app.jar"]
