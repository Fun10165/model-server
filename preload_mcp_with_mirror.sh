#!/bin/bash
# preload_mcp_with_mirror.sh

echo "🚀 设置镜像源..."

# 设置 uv 镜像
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 设置 npm 镜像
npm config set registry https://registry.npmmirror.com/

echo "📦 开始预加载 MCP 依赖..."

# 你可以把之前的 preload_mcp.py 改成 shell 版本，或继续用 Python
uv run preload_mcp.py

echo "✅ 预加载完成，MCP 启动将更快！"
