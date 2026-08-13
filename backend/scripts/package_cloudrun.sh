#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd "$(dirname "$0")/.." && pwd)"
timestamp="$(date +%Y%m%d-%H%M%S)"
output="${1:-$backend_dir/pinco-backend-upload-$timestamp-safe.zip}"

cd "$backend_dir"
zip -j "$output" Dockerfile main.py state_store.py career_taxonomy.py requirements.txt admin_console.html
echo "$output"
