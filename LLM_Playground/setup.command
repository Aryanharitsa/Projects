#!/bin/bash
set -euo pipefail

# Always start from the script’s own directory
cd "$(dirname "$0")"

echo "─── LLM Playground Setup ───"

# 1. FRONTEND SETUP
if [ -d "llm_playground_frontend" ]; then
  echo "Setting up frontend (npm)..."
  cd llm_playground_frontend
  npm install --legacy-peer-deps || { echo "npm install failed!"; exit 1; }
  cd ..
else
  echo "❌ Frontend directory not found!"
  exit 1
fi

# 2. BACKEND SETUP
if [ -d "llm_playground_backend" ]; then
  echo "Setting up backend (Python venv)..."
  cd llm_playground_backend
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt || { echo "pip install failed!"; deactivate; exit 1; }
  deactivate
  cd ..
else
  echo "❌ Backend directory not found!"
  exit 1
fi

echo "✅ Setup complete!"
read -n 1 -s -r -p $'Press any key to close…\n'