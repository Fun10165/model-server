# src/app/config.py
import os
from typing import Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict

# 获取脚本的基础目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) # 这将是 'src' 目录

class Settings(BaseSettings):
    # 从项目的根目录（'src' 的上一级）加载 .env 文件
    model_config = SettingsConfigDict(env_file=os.path.join(BASE_DIR, '..', '.env'), extra='ignore')

    # --- 服务器配置 ---
    HOST_NAME: str = "0.0.0.0"
    SERVER_PORT: int = 8443
    FILES_DIR: str = os.path.join(BASE_DIR, '..', 'files')
    TEMP_DIR: str = os.path.join(BASE_DIR, '..', 'temp')

    # --- 火山引擎 API 凭证 ---
    VOLC_APPID: str | None = None
    VOLC_TOKEN: str | None = None

    # --- OpenAI 兼容 API 配置 ---
    OPENAI_API_KEY: str | None = None
    OPENAI_API_BASE_URL: str | None = None
    MODEL_NAME: str = "deepseek-v3-250324"

    ARK_API_KEY: str | None = None

    # --- 日志配置 ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "server.log"

    # --- 音频处理配置 ---
    COMPATIBLE_AUDIO_FORMATS: tuple[str, ...] = ('.wav', '.mp3', '.ogg')
    DOWNLOAD_TIMEOUT: int = 60
    FFMPEG_TIMEOUT: int = 180

    # --- 火山引擎 API 配置 ---
    VOLC_SUBMIT_URL: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    VOLC_QUERY_URL: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    QUERY_INITIAL_SLEEP: int = 3
    QUERY_MAX_SLEEP: int = 30
    QUERY_FACTOR: float = 1.5

    # --- 任务重试配置 ---
    TASK_MAX_RETRIES: int = 3
    TASK_RETRY_DELAY: int = 15
    
    # --- 新增：MCP 服务配置 ---
    MCP_FILESYSTEM_ALLOWED_PATH: str = "./files"

    # --- 新增：讯飞 AIPPT API 凭证 ---
    XF_AIPPT_APP_ID: str | None = None
    XF_AIPPT_API_SECRET: str | None = None

    mcp_config: Dict[str,Any] = {
    "mcpServers": {
        "filesystem": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", MCP_FILESYSTEM_ALLOWED_PATH]
        },
        "excel": {
            "command": "uvx",
            "args": ["excel-mcp-server", "stdio"]
        },
        "word-document-server": {
            "command": "uvx",
            "args": ["--from", "office-word-mcp-server", "word_mcp_server"]
        },
        "fetch":{
            "command": "uvx",
            "args": ["mcp-server-fetch"]
        },
        "git":{
            "command": "uvx",
            "args": ["mcp-server-git"]
        },
        "sequential-thinking": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
        },
        "time":{
            "command": "uvx",
            "args": ["mcp-server-time"]
        },
        "memory": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"]
        },
        "Pydantic Run Python":{
            "transport": "stdio",
            "command": "deno",
            "args": ["run","-N","-R=node_modules","-W=node_modules","--node-modules-dir=auto","jsr:@pydantic/mcp-run-python","stdio"]
        },
        "context7": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp@latest"]
        },
    }
    }
    
    # (可以放在文件末尾，class 定义之内即可)

# 创建一个可供全局导入的 settings 单例
settings = Settings()