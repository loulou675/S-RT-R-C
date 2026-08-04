#!/bin/zsh

cd "$(dirname "$0")" || exit 1

export PATH="/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH"
export VITE_USE_MOCK_VISION=true

URL="http://127.0.0.1:5176/"

if curl -fsS "$URL" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

(sleep 1.2 && open "$URL") &
pnpm dev --host 127.0.0.1 --port 5176 --strictPort
