#!/usr/bin/env bash
set -e

echo "🚀 Building AgentTrace Desktop..."

# Build frontend
echo "📦 Building frontend..."
cd web
pnpm install
pnpm build
cd ..

# Build Tauri
echo "🔨 Building Tauri..."
cd src-tauri
cargo tauri build
cd ..

echo "✅ Build complete!"
echo "📁 Output: src-tauri/target/release/bundle/"
