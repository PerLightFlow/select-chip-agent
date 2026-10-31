#!/usr/bin/env bash
# Execute on the build host, before release packaging; does not touch services.
set -euo pipefail
root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
output_dir=${SOLEX_BUILD_OUTPUT:-/data/solexai/yongjun/build-cache/solex-managed-runtime}
builder_image=${SOLEX_GO_BUILDER_IMAGE:-golang:1.26-bookworm@sha256:23ce71337b726608afb1bc00986e630a05034a87a87ea1fc2cd1ae5cf33387eb}
source_commit=${SOLEX_SOURCE_COMMIT:-}
if [[ -z "$source_commit" ]]; then
  source_commit=$(git -C "$root_dir" rev-parse HEAD)
  if [[ -n "$(git -C "$root_dir" status --porcelain --untracked-files=normal)" ]]; then
    echo 'Refusing to label a dirty tree as a clean commit. Commit first or provide SOLEX_SOURCE_COMMIT for an explicitly identified source snapshot.' >&2
    exit 1
  fi
fi
if [[ ! "$source_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'SOLEX_SOURCE_COMMIT must be a full Git commit ID.' >&2
  exit 1
fi
mkdir -p "$output_dir"
# The build host has Docker's classic builder. Dependencies remain in image
# layers, including /go/pkg/mod, so subsequent builds and test containers reuse
# them without requiring buildx or a cache mount.
artifact_image="solex-managed-runtime:builder-$source_commit"
artifact_container=
cleanup() {
  if [[ -n "$artifact_container" ]]; then
    docker rm "$artifact_container" >/dev/null
  fi
}
trap cleanup EXIT
DOCKER_BUILDKIT=0 docker build \
  --network "${SOLEX_BUILD_NETWORK:-host}" \
  --file "$root_dir/deploy/solex-runtime/Dockerfile.builder" \
  --target builder \
  --tag "$artifact_image" \
  --build-arg "GO_BUILDER_IMAGE=$builder_image" \
  --build-arg "SOURCE_COMMIT=$source_commit" \
  --build-arg "SOURCE_VERSION=${SOLEX_SOURCE_VERSION:-solex-managed-runtime}" \
  --build-arg "BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg "GOPROXY=${SOLEX_GOPROXY:-https://proxy.golang.org,direct}" \
  --build-arg "GOSUMDB=${SOLEX_GOSUMDB:-sum.golang.org}" \
  --build-arg "RUST_BUILDER_IMAGE=${SOLEX_RUST_BUILDER_IMAGE:-rust:bookworm@sha256:9181b56c2a21ab1d5e73cffe04fc762426d30aa7fac3c91141dd033f49a7fc8b}" \
  "$root_dir"
artifact_container=$(docker create --entrypoint /bin/true "$artifact_image")
docker cp "$artifact_container:/out/." "$output_dir/"
test -s "$output_dir/WeKnora"
grep -Fq -- "-tags=anydoc" "$output_dir/go-build-info.txt"
grep -Fq "internal/handler.CommitID=$source_commit" "$output_dir/go-build-info.txt"
if grep -q 'not found' "$output_dir/runtime-libraries.txt"; then
  echo 'The binary has unresolved runtime libraries.' >&2
  exit 1
fi
# Recalculate using a relative filename for a portable release manifest.
(cd "$output_dir" && sha256sum WeKnora > WeKnora.sha256)
printf 'Built Debian 12 CGO + AnyDoc binary at %s/WeKnora\n' "$output_dir"
