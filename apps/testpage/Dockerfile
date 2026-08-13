# 파이프라인 전 구간(빌드 → ECR → Argo → ALB)을 확인하기 위한 정적 페이지다.
# 빌드 단계가 없으므로 멀티스테이지도 필요 없다.
#
# nginx 공식 이미지 대신 unprivileged 변형을 쓴다. 공식 이미지는 root로 시작해
# 워커만 내려놓는 구조라 매니페스트의 runAsNonRoot: true 와 부딪힌다.
# 이 변형은 처음부터 UID 101로 돌고 8080을 듣는다.

FROM nginxinc/nginx-unprivileged:1.31-alpine

COPY --chown=101:101 index.html /usr/share/nginx/html/index.html

USER 101
EXPOSE 8080
