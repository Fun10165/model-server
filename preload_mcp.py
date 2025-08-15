import subprocess
import os

# 定义所有需要预加载的命令
commands = [
    ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
    ["uvx", "excel-mcp-server"],
    ["uvx", "mcp-server-fetch"],
    ["uvx", "mcp-server-git"],
    ["uvx", "mcp-server-time"],
    ["deno", "run", "-N", "-R=node_modules", "-W=node_modules", "--node-modules-dir=auto", "jsr:@pydantic/mcp-run-python"],
    ["npx", "-y", "@upstash/context7-mcp@latest"],

    ["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
    ["uvx", "--from", "office-word-mcp-server", "word_mcp_server"],
    ["npx", "-y", "@modelcontextprotocol/server-memory"],
]

def preload():
    for cmd in commands:
        print(f"Preloading: {' '.join(cmd)}")
        try:
            # 只运行 --help 或 --version 来触发缓存，不实际启动服务
            subprocess.run(cmd + ["--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except subprocess.TimeoutExpired:
            print(f"⚠️ Timeout for {cmd[0]} - 可能已缓存")
        except Exception as e:
            print(f"❌ Failed to preload {cmd}: {e}")

if __name__ == "__main__":
    print("最后三个服务器由于配置问题，在非初次Preload时会发生超时，但实际已缓存完毕。")
    preload()
