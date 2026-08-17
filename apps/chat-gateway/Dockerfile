# 빌드 산출물(dist)과 운영 의존성만 런타임에 넘긴다.
# 타입스크립트 컴파일러와 타입 정의는 실행에 필요 없고, 이미지에 남으면
# 취약점 표면만 넓어진다.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM node:22-alpine
WORKDIR /app

# npm 과 corepack 을 지운다. 실행은 `node dist/main.js` 라 둘 다 필요 없는데,
# 이미지에 남아 있으면 그 안에 번들된 의존성이 그대로 취약점으로 잡힌다
# (CVE-2026-59873 은 npm 이 들고 있는 tar 다). 우리 package.json 으로는
# 고칠 수 없고 베이스 이미지가 갱신돼야 사라지므로, 안 쓰는 것을 지우는 편이
# 확실하다. 이미지도 작아진다.
RUN rm -rf /usr/local/lib/node_modules/npm \
           /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭).
# node 이미지의 기본 node 사용자가 1000번이다.
USER 1000

EXPOSE 8080

# dd-trace 를 --require 로 먼저 올린다. 소스에서 임포트하지 않는 이유는
# 파이썬 쪽 ddtrace-run 과 같다 — 끄고 켤 때 이미지를 다시 만들지 않는다.
#
# WebSocket 은 HTTP 요청처럼 트레이스가 잡히지 않는다. 업그레이드 요청 한 번이
# 전부이고 그 뒤 프레임은 트레이스 밖이다. 여기서 얻는 것은 Valkey Pub/Sub
# 호출 시간과 런타임 지표다.
CMD ["node", "--require", "dd-trace/init", "dist/main.js"]
