#!/bin/bash
# AgentTrace Desktop — macOS 一键安装脚本
# 用法: ./scripts/setup-mac.sh

set -e

echo "═══════════════════════════════════════════════"
echo "  AgentTrace Desktop 安装脚本 (macOS)"
echo "═══════════════════════════════════════════════"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.9+"
    echo "   推荐: brew install python@3.11"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python 版本: $PYTHON_VERSION"

# 检查 Rust
if ! command -v cargo &> /dev/null; then
    echo "❌ 未找到 cargo，请先安装 Rust"
    echo "   运行: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

RUST_VERSION=$(cargo --version 2>&1 | awk '{print $2}')
echo "✓ Rust 版本: $RUST_VERSION"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ 未找到 node，请先安装 Node.js 20+"
    echo "   推荐: brew install node@20"
    exit 1
fi

NODE_VERSION=$(node --version 2>&1)
echo "✓ Node.js 版本: $NODE_VERSION"

# 检查 pnpm
if ! command -v pnpm &> /dev/null; then
    echo "📦 安装 pnpm..."
    npm install -g pnpm
fi

PNPM_VERSION=$(pnpm --version 2>&1)
echo "✓ pnpm 版本: $PNPM_VERSION"

echo ""
echo "───────────────────────────────────────────────"
echo " 1/4 安装 Python 依赖"
echo "───────────────────────────────────────────────"
cd "$(dirname "$0")/.."
pip3 install -e ".[desktop]" -q

# 检查 cozeloop SDK
if python3 -c "import cozeloop" 2>/dev/null; then
    echo "✓ cozeloop SDK 已安装"
else
    echo "⚠️ cozeloop SDK 未安装，Trace 上报功能将不可用"
    echo "   如需使用，运行: pip3 install cozeloop"
fi

echo ""
echo "───────────────────────────────────────────────"
echo " 2/4 安装前端依赖"
echo "───────────────────────────────────────────────"
cd web
pnpm install

echo ""
echo "───────────────────────────────────────────────"
echo " 3/4 构建前端"
echo "───────────────────────────────────────────────"
pnpm build

echo ""
echo "───────────────────────────────────────────────"
echo " 4/4 构建桌面应用"
echo "───────────────────────────────────────────────"
cd ../src-tauri
cargo build --release

APP_PATH="$(pwd)/target/release/bundle/macos/AgentTrace.app"
DMG_PATH="$(pwd)/target/release/bundle/dmg"

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ 构建完成!"
echo "═══════════════════════════════════════════════"
echo ""

if [ -d "$APP_PATH" ]; then
    echo "  📦 App 包: $APP_PATH"
    echo "     可直接双击打开，或拖入 Applications 文件夹"
fi

if [ -d "$DMG_PATH" ]; then
    DMG_FILE=$(ls "$DMG_PATH"/*.dmg 2>/dev/null | head -1)
    if [ -n "$DMG_FILE" ]; then
        echo "  💿 DMG 包: $DMG_FILE"
    fi
fi

echo ""
echo "  🚀 快速启动（开发模式）:"
echo "     cd src-tauri && cargo tauri dev"
echo ""
echo "  📝 配置 CozeLoop:"
echo "     打开应用后，在 Settings 页面配置 Workspace ID 和 API Token"
echo ""
