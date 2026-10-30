# Retain the deployed API/SSE/WebSocket proxy and runtime config entrypoint.
ARG RUNTIME_IMAGE=wechatopenai/weknora-ui@sha256:df26705d866997db07f3da78dabedc4f594b383566a3996810c166a5c6bee393
FROM ${RUNTIME_IMAGE}
ARG RELEASE_ID
ARG SOURCE_REVISION
LABEL org.opencontainers.image.title="SOLEX" \
      org.opencontainers.image.description="SOLEX knowledge workspace frontend" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      io.solex.ui.release="${RELEASE_ID}"
# Remove every old bundle and branded public asset before installing this build.
RUN rm -rf /usr/share/nginx/html && mkdir -p /usr/share/nginx/html
COPY dist/ /usr/share/nginx/html/
COPY 50x.html /usr/share/nginx/html/50x.html
# Inherit /docker-entrypoint.sh; do not replace the upstream proxy configuration.
