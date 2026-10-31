#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
sha256sum --check --status SHA256SUMS
exec python3 deploy.py
