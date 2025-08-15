# --- START OF FILE langgraph_client.py ---

import asyncio
from typing import Literal, Optional
from fastmcp import Client
from langchain_core.messages import AIMessage
from langchain_ark import ChatArk
from langchain_mcp_adapters.tools import load_mcp_tools
from fastmcp.client.roots import RequestContext
from langgraph.prebuilt import create_react_agent
import traceback
from ..config import settings
from langchain_core.runnables import RunnableConfig
config = RunnableConfig(recursion_limit=128)

# --- ANSI 颜色代码 ---
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RED = '\033[91m'
    ENDC = '\033[0m'

def color_print(text, color: Literal["green", "yellow", "blue", "red"]):
    """为终端输出添加颜色"""
    color_code = getattr(Colors, color.upper())
    print(f"{color_code}{text}{Colors.ENDC}", flush=True)

# MCP 服务器配置 (保持不变)
mcp_config=settings.mcp_config

# --- 新增: 全局变量来持有 Client 和 Agent 实例 ---
# 这些变量将在服务器启动时被填充一次
mcp_client_instance: Optional[Client] = None
agent_instance = None

async def roots_callback(context: RequestContext) -> list[str]:
    print(f"Server requested roots (Request ID: {context.request_id})")
    return ["file://./files/"]

async def initialize_mcp_and_agent():
    """
    (新增) 初始化 fastmcp.Client 和 LangGraph Agent。
    这个函数应该在 Web 服务器启动时被调用一次。
    """
    global mcp_client_instance, agent_instance
    
    # 防止重复初始化
    if agent_instance is not None:
        color_print("--- [信息] MCP 和 Agent 已初始化，跳过。", "yellow")
        return

    try:
        color_print("--- [步骤 1] 正在初始化 MCP Client...", "blue")
        mcp_client = Client(transport=mcp_config,roots=roots_callback)
        # 启动客户端会话，这会启动所有配置的 MCP 服务器子进程
        await mcp_client.__aenter__() 
        mcp_client_instance = mcp_client
        
        color_print("--- [步骤 2] 正在加载 MCP 工具...", "blue")
        tools = await load_mcp_tools(mcp_client.session)
        
        color_print(f"--- [步骤 3] 工具加载成功 ({len(tools)}个)。正在创建 Agent...", "blue")
        llm = ChatArk(model="kimi-k2-250711", max_tokens=32767,api_key=settings.ARK_API_KEY)
        agent_instance = create_react_agent(llm, tools)
        
        color_print("--- [成功] MCP Client 和 Agent 已成功启动并准备就绪。", "green")

    except Exception as e:
        color_print("\n--- [严重错误] 初始化 MCP 或 Agent 期间发生异常 ---", "red")
        color_print(f"错误类型: {type(e).__name__}", "red")
        color_print(f"错误信息: {e}", "red")
        color_print("堆栈跟踪:", "red")
        traceback.print_exc()
        color_print("---------------------------------------", "red")
        # 如果初始化失败，确保实例为空
        mcp_client_instance = None
        agent_instance = None
        raise e # 重新抛出异常，让上层知道启动失败

async def shutdown_mcp_client():
    """
    (新增) 关闭 MCP Client，终止所有子进程。
    这个函数应该在 Web 服务器关闭时被调用。
    """
    global mcp_client_instance
    if mcp_client_instance:
        color_print("--- [关闭] 正在关闭 MCP Client...", "yellow")
        await mcp_client_instance.__aexit__(None, None, None)
        mcp_client_instance = None
        color_print("--- [关闭] MCP Client 已成功关闭。", "green")

async def process_mcp_query(question: str) -> str:
    """
    (修改) 使用预先初始化的 Agent 处理单个请求。
    这个函数将从 Web 请求处理器中被调用。
    """
    final_answer = ""
    if not agent_instance:
        error_message = "错误：MCP Agent 未初始化。请先启动服务器。"
        color_print(error_message, "red")
        return error_message

    try:
        color_print(f"--- [处理中] 使用预初始化的 Agent 处理请求: '{question}'...", "blue")
        
        # 直接使用全局 agent 实例
        final_output = await agent_instance.ainvoke({"messages": [("user", question)]},config)
        
        color_print("--- [处理完毕] Agent 处理完成。", "green")

        if final_output and isinstance(final_output, dict):
            messages = final_output.get('messages', [])
            if messages and isinstance(messages, list):
                last_message = messages[-1]
                if isinstance(last_message, AIMessage) and last_message.content:
                    final_answer = last_message.content

    except Exception as e:
        color_print("\n--- [严重错误] Agent 执行期间发生异常 ---", "red")
        traceback.print_exc()
        final_answer = f"Agent 执行时发生错误: {e}"

    return final_answer

# src/app/services/mcp_agent_manager.py
# ... (在文件末尾添加) ...
def is_agent_ready() -> bool:
    """检查 Agent 实例是否已成功初始化"""
    return agent_instance is not None

async def main():
    """
    (修改) 用于独立测试此模块的功能。
    """
    try:
        # 1. 初始化
        await initialize_mcp_and_agent()

        # 2. 运行一个或多个查询
        question = "browse the directories allowed."
        result = await process_mcp_query(question)
        
        print("\n" + "="*50)
        color_print("Agent 的最终回答:", "green")
        print(result)
        print("="*50)
        
    finally:
        # 3. 关闭
        await shutdown_mcp_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n操作已由用户取消。")