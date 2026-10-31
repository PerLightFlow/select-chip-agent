# syntax=docker/dockerfile:1
# Build from the repository root. This stage is only for pre-release builds;
# the production release installs its exported binary onto the pinned runtime.
ARG GO_BUILDER_IMAGE=golang:1.26-bookworm@sha256:23ce71337b726608afb1bc00986e630a05034a87a87ea1fc2cd1ae5cf33387eb
FROM ${GO_BUILDER_IMAGE} AS go-dependencies
WORKDIR /src/weknora

ARG GOPROXY=https://proxy.golang.org,direct
ARG GOSUMDB=sum.golang.org
ARG RUST_TOOLCHAIN=stable
ENV CGO_ENABLED=1 \
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
    && go mod download && go mod verify \
    && sha256sum -c /tmp/go-locks.sha256

FROM go-dependencies AS dependencies
ARG RUST_TOOLCHAIN=stable
ARG RUSTUP_INIT_URL=https://sh.rustup.rs
ARG RUSTUP_DIST_SERVER=https://static.rust-lang.org
ARG RUSTUP_UPDATE_ROOT=https://static.rust-lang.org/rustup
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential pkg-config libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf "${RUSTUP_INIT_URL}" -o /tmp/rustup-init.sh \
    && RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER}" RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT}" \
       sh /tmp/rustup-init.sh -y --profile minimal --default-toolchain "${RUST_TOOLCHAIN}" \
    && rm /tmp/rustup-init.sh

FROM dependencies AS builder
COPY weknora/ ./

# Keep the native AnyDoc engine: its static archive is linked into the binary
# and cannot be recovered from the currently running app image.
RUN bash scripts/build-anydoc-lib.sh

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
