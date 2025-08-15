# src/app/main.py
import logging
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
 
from .config import settings
from .services import mcp_agent_manager
from .api import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 应用启动时执行 ---
    # 1. 配置日志
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(settings.LOG_FILE, 'a', 'utf-8')
        ]
    )
    # 2. 确保目录存在
    for dir_path in [settings.FILES_DIR, settings.TEMP_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            logging.info(f"已创建目录: {dir_path}")
    
    # 3. 在后台初始化 MCP 服务
    logging.info("应用正在启动，开始初始化 MCP 服务...")
    asyncio.create_task(mcp_agent_manager.initialize_mcp_and_agent())
    
    yield # 应用在此处运行
    
    # --- 应用关闭时执行 ---
    logging.info("应用正在关闭...")
    await mcp_agent_manager.shutdown_mcp_client()
    logging.info("MCP 服务已优雅关闭。")

app = FastAPI(
    title="多模态 AI 服务器 (重构版)",
    description="一个用于处理视觉、音频和 MCP 任务的服务器，采用现代 FastAPI 架构。",
    version="2.0.0",
    lifespan=lifespan
)

# 挂载 API 路由
app.include_router(api_router.router)

# 挂载静态文件目录，以服务于转写后的音频文件
app.mount("/files", StaticFiles(directory=settings.FILES_DIR), name="files")

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "message": "欢迎使用 AI 服务器 v2.0!"}