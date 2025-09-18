#!/bin/bash
set -euo pipefail

# Always start from script’s directory
cd "$(dirname "$0")"

echo "—— Running Deep's LLM Playground ——"

# Make sure both command files exist
if [[ ! -f "llm_playground_backend_start.command" ]]; then
  echo "❌ Backend launch script not found!"
  exit 1
fi

if [[ ! -f "llm_playground_frontend_start.command" ]]; then
  echo "❌ Frontend launch script not found!"
  exit 1
fi

# Launch BACKEND in a new Terminal window
echo "▶ Launching backend..."
open -a Terminal "`pwd`/llm_playground_backend_start.command"

# Launch FRONTEND in a new Terminal window
echo "▶ Launching frontend..."
open -a Terminal "`pwd`/llm_playground_frontend_start.command"

echo "✅ Both backend and frontend are starting in separate Terminal windows!"
read -n 1 -s -r -p $'Press any key to close this launcher window…\n'