# syntax=docker/dockerfile:1
# Build from the repository root. This stage is only for pre-release builds;
# the production release installs its exported binary onto the pinned runtime.
ARG GO_BUILDER_IMAGE=golang:1.26-bookworm@sha256:23ce71337b726608afb1bc00986e630a05034a87a87ea1fc2cd1ae5cf33387eb
ARG RUST_BUILDER_IMAGE=rust:bookworm@sha256:9181b56c2a21ab1d5e73cffe04fc762426d30aa7fac3c91141dd033f49a7fc8b
FROM ${GO_BUILDER_IMAGE} AS go-dependencies
WORKDIR /src/weknora

ARG GOPROXY=https://proxy.golang.org,direct
ARG GOSUMDB=sum.golang.org
ENV CGO_ENABLED=1 \
    GOMAXPROCS=4 \
    CARGO_BUILD_JOBS=4 \
    GOFLAGS=-mod=readonly \
    GOTOOLCHAIN=local \
    GOPROXY=${GOPROXY} \
    GOSUMDB=${GOSUMDB} \
    RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo \
    PATH=/opt/cargo/bin:$PATH
COPY weknora/go.mod weknora/go.sum ./
COPY weknora/third_party/anydoc-go/go.mod third_party/anydoc-go/go.mod
RUN sha256sum go.mod go.sum > /tmp/go-locks.sha256 \
    && go list -m -f '{{if not .Main}}{{if .Replace}}{{if .Replace.Version}}{{.Replace.Path}}@{{.Replace.Version}}{{end}}{{else}}{{.Path}}@{{.Version}}{{end}}{{end}}' all > /tmp/go-all-modules \
    && awk -v platform="$(go env GOOS)-$(go env GOARCH)" \
         'NF && ($0 !~ /^github.com\/duckdb\/duckdb-go-bindings\/lib\// || index($0, "/" platform "@"))' \
       /tmp/go-all-modules > /tmp/go-modules \
    && xargs go mod download < /tmp/go-modules && go mod verify \
    && sha256sum -c /tmp/go-locks.sha256

FROM ${RUST_BUILDER_IMAGE} AS rust-toolchain

FROM go-dependencies AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential pkg-config libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=rust-toolchain /usr/local/rustup /opt/rustup
COPY --from=rust-toolchain /usr/local/cargo /opt/cargo
RUN rustc --version && cargo --version

FROM dependencies AS builder
COPY weknora/third_party/anydoc-go/ third_party/anydoc-go/
COPY weknora/scripts/build-anydoc-lib.sh scripts/build-anydoc-lib.sh

# Keep the native AnyDoc engine: its static archive is linked into the binary
# and cannot be recovered from the currently running app image.
RUN bash scripts/build-anydoc-lib.sh
COPY weknora/ ./

ARG SOURCE_COMMIT
ARG SOURCE_VERSION=solex-managed-runtime
ARG BUILD_TIME
RUN test -n "${SOURCE_COMMIT}" && test -n "${BUILD_TIME}" \
    && mkdir -p /out \
    && COMMIT_ID="${SOURCE_COMMIT}" VERSION="${SOURCE_VERSION}" \
       BUILD_TIME="${BUILD_TIME}" GO_VERSION="$(go version)" \
       make build-prod GO_BUILD_TAGS=anydoc BINARY_NAME=/out/WeKnora \
    && go version -m /out/WeKnora > /out/go-build-info.txt \
    && grep -Fq -- '-tags=anydoc' /out/go-build-info.txt \
    && grep -Fq "internal/handler.CommitID=${SOURCE_COMMIT}" /out/go-build-info.txt \
    && ldd /out/WeKnora > /out/runtime-libraries.txt \
    && ! grep -q 'not found' /out/runtime-libraries.txt \
    && rustc --version > /out/rust-toolchain.txt \
    && sha256sum /out/WeKnora > /out/WeKnora.sha256

FROM scratch AS artifact
COPY --from=builder /out/ /
