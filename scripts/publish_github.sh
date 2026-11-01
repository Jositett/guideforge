#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-guideforge}"
VISIBILITY="${2:---public}"

echo "==> Checking GitHub CLI authentication..."
gh auth status

if [ ! -d .git ]; then
  git init -b main
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -m "feat: 100% open-source GuideForge uv project with polyglot Node/Python/Go/Rust support"
fi

echo "==> Creating GitHub repository '${REPO_NAME}' (${VISIBILITY}) and pushing..."
gh repo create "${REPO_NAME}" "${VISIBILITY}" \\
  --source=. \\
  --remote=origin \\
  --description "100% open-source client & developer manual generator with polyglot code runner (Node, Python, Go, Rust)" \\
  --push
