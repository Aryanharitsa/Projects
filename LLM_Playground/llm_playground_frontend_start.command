#!/bin/bash
set -euo pipefail

# Always run from this script’s directory
cd "$(dirname "$0")/llm_playground_frontend"

echo "🚀 Starting Frontend Dev Server..."
npm run dev