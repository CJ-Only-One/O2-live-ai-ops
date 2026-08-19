// /hls 외의 경로를 엣지에서 끊는다.
//
// 이 배포는 영상만 통과시킨다. API 나 프론트가 여기로 들어오면 두 가지가
// 깨진다 — 캐시 정책이 플레이리스트 기준(TTL 1~2초)이라 API 응답이 잠깐
// 캐시될 수 있고, 오리진 커스텀 헤더의 CDN 비밀값이 그 경로까지 실려 간다.
//
// 경로 패턴으로 /hls/* 만 오리진에 보내고, 나머지는 여기서 403 으로 끊는다.
// 오리진까지 가지 않으므로 요금도 안 나간다.
function handler(event) {
  return {
    statusCode: 403,
    statusDescription: 'Forbidden',
    headers: {
      'content-type': { value: 'text/plain; charset=utf-8' },
    },
    body: '이 배포는 /hls 경로만 제공합니다.',
  };
}
