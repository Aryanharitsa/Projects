#!/bin/bash
set -euo pipefail

# Go to backend dir
cd "$(dirname "$0")/llm_playground_backend"

echo "🐍 Activating Python venv..."
source venv/bin/activate

echo "🚀 Starting Backend API..."
python src/main.py