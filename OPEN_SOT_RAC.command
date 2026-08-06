#!/bin/zsh

set -e

cd "$(dirname "$0")" || exit 1

if [[ -z "${VITE_USE_MOCK_VISION+x}" ]]; then
  if [[ -f public/models/waste_classifier.onnx && -f public/models/labels.json ]]; then
    export VITE_USE_MOCK_VISION=false
  else
    export VITE_USE_MOCK_VISION=true
  fi
fi

URL="http://127.0.0.1:5173/"
pnpm_command="$(command -v pnpm || true)"
node_command="$(command -v node || true)"

if [[ -z "$node_command" && -n "$pnpm_command" ]]; then
  pnpm_directory="$(cd "$(dirname "$pnpm_command")" && pwd)"
  bundled_node="${pnpm_directory}/../../node/bin/node"
  if [[ -x "$bundled_node" ]]; then
    node_command="$bundled_node"
  fi
fi

if [[ -z "$pnpm_command" ]]; then
  echo "pnpm is required. Install it with: corepack enable"
  read -r "?Press Return to close..."
  exit 1
fi

if [[ -z "$node_command" ]]; then
  echo "Node.js is required. Install Node.js 22 or newer, then try again."
  read -r "?Press Return to close..."
  exit 1
fi

if [[ ! -d node_modules ]]; then
  "$pnpm_command" install
fi

if curl -fsS "$URL" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

(sleep 1.2 && open "$URL") &
"$node_command" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort
