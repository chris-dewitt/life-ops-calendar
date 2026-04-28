#!/bin/bash
set -euo pipefail

# Only run in Claude Code remote/cloud sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Configure git credentials from GITHUB_TOKEN env var (set in ~/.claude/settings.json)
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global credential.helper store
  echo "https://chris-dewitt:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
  chmod 600 ~/.git-credentials
fi

# Install Python dependencies
pip install -r "${CLAUDE_PROJECT_DIR}/requirements.txt" --quiet
