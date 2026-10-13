#!/usr/bin/env bash
# Regenerate apps/web/openapi.json and apps/web/src/api/schema.d.ts (see gen_api_client.mjs).
set -euo pipefail
cd "$(dirname "$0")/.."
exec node scripts/gen_api_client.mjs "$@"
