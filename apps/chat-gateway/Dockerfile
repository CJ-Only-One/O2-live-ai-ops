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

COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./

# 숫자 UID로 실행 (비root, K8s securityContext의 runAsNonRoot와 매칭).
# node 이미지의 기본 node 사용자가 1000번이다.
USER 1000

EXPOSE 8080

CMD ["node", "dist/main.js"]
