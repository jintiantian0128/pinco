#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
target="${1:-}"

if [[ -z "$target" ]]; then
  echo "Usage: $0 <empty-target-directory>" >&2
  exit 2
fi

mkdir -p "$target"
if [[ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Target directory must be empty: $target" >&2
  exit 2
fi

copy_file() {
  local source="$1"
  local destination="$target/$1"
  mkdir -p "$(dirname "$destination")"
  cp "$project_dir/$source" "$destination"
}

copy_tree() {
  local source="$1"
  mkdir -p "$target/$source"
  rsync -a \
    --exclude '.DS_Store' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "$project_dir/$source/" "$target/$source/"
}

for file in \
  .gitignore \
  README.md \
  DEVELOPMENT_ENTRYPOINT.md \
  STATUS.md \
  docs/DEPENDENCY_SECURITY_2026-08-13.md \
  docs/LEGACY_ASSET_MIGRATION_2026-08-13.md \
  docs/OPEN_SOURCE_ADOPTION_2026-08-04.md \
  docs/PMF_IMPLEMENTATION_STATUS_2026-08-05.md \
  docs/TECHNICAL_DESIGN.md \
  backend/.dockerignore \
  backend/.env.example \
  backend/.gitignore \
  backend/DEPLOY_CLOUDRUN.md \
  backend/Dockerfile \
  backend/admin_console.html \
  backend/career_taxonomy.py \
  backend/main.py \
  backend/requirements-local-asr.txt \
  backend/requirements.txt \
  backend/state_store.py \
  backend/test_admin_console.py \
  backend/test_career_taxonomy.py \
  backend/test_conversation_agent.py \
  backend/test_pilot_feedback.py \
  backend/test_state_store_mysql.py \
  backend/test_trust_foundation.py \
  backend/scripts/package_cloudrun.sh \
  backend/scripts/smoke_local_session.py \
  pinco-miniapp/babel.config.js \
  pinco-miniapp/critical-flows.test.mjs \
  pinco-miniapp/package-lock.json \
  pinco-miniapp/package.json \
  pinco-miniapp/project.config.json \
  pinco-miniapp/project.tt.json \
  pinco-miniapp/tsconfig.json \
  scripts/prepare_github_release.sh
do
  copy_file "$file"
done

copy_tree pinco-miniapp/config
copy_tree pinco-miniapp/src
copy_tree pinco-miniapp/types

echo "$target"
