# 仅供调试环境用
# 设置镜像
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
npm config set registry https://registry.npmmirror.com/
uv run uvicorn src.app.main:app --host 0.0.0.0 --port 8443  --reload
