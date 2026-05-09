#!/usr/bin/env bash
set -e

echo "🚀 Starting AgentTrace Desktop in dev mode..."

# Install dependencies if needed
if [ ! -d "web/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd web && pnpm install && cd ..
fi

# Start Tauri dev (will also start frontend dev server via beforeDevCommand)
cd src-tauri
cargo tauri dev
