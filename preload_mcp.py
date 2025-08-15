import asyncio
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

async def run_command(cmd):
    """
    异步执行单个预加载命令。
    """
    cmd_str = ' '.join(cmd)
    print(f"Preloading: {cmd_str}")
    try:
        # 异步创建子进程
        proc = await asyncio.create_subprocess_exec(
            *(cmd + ["--help"]),  # 将 --help 参数添加到命令中
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        # 等待进程完成，并设置30秒超时
        await asyncio.wait_for(proc.wait(), timeout=30)

    except asyncio.TimeoutError:
        print(f"⚠️ Timeout for {cmd[0]} - 可能已缓存")
        # 如果超时，确保进程被终止
        if proc.returncode is None:
            try:
                proc.terminate()
                await proc.wait()
            except ProcessLookupError:
                # 进程可能在我们尝试终止它之前就已经结束了
                pass
    except Exception as e:
        print(f"❌ Failed to preload {cmd[0]}: {e}")

async def main():
    """
    并发运行所有预加载命令。
    """
    # 为列表中的每个命令创建一个异步任务
    tasks = [run_command(cmd) for cmd in commands]
    # 使用 asyncio.gather 并发执行所有任务
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    print("最后三个服务器由于配置问题，在非初次Preload时会发生超时，但实际已缓存完毕。")
    # 运行主异步函数
    asyncio.run(main())