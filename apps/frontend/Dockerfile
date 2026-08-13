# 빌드 산출물(정적 파일)만 nginx로 서빙한다.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Vite의 VITE_* 환경변수는 런타임이 아니라 빌드 시점에 번들에 박힌다.
# 빌드 인자로 안 받으면 프로덕션 빌드에서 API 주소가 undefined로 굳어버린다.
# CI에서 --build-arg VITE_API_BASE_URL=<실제 API 도메인> 으로 넘겨줘야 한다.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# nginx 공식 이미지는 root로 시작해 K8s의 runAsNonRoot: true와 부딪힌다.
# unprivileged 변형은 처음부터 UID 101로 돌고 8080을 듣는다.
FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY --from=build --chown=101:101 /app/dist /usr/share/nginx/html

USER 101
EXPOSE 8080
