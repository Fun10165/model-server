# src/app/schemas/tasks.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Any
from .volc import TranscriptionOptions # <--- 新增导入
# --- 通用任务模型 ---

class TaskCreationResponse(BaseModel):
    """当以轮询模式创建任务时，返回的响应模型"""
    task_id: str = Field(..., description="用于查询任务状态的唯一ID")

class TaskStatusResponse(BaseModel):
    """查询任务状态时的响应模型"""
    task_id: str
    status: str = Field(..., description="任务状态 (e.g., pending, processing, completed, failed)")
    result: Any | None = None # 使用 Any 来容纳各种可能的结果类型

# --- API 输入模型 ---

class VisionRequest(BaseModel):
    """图像分析请求的模型"""
    prompt: str = Field(..., description="给模型的指令或问题", alias="INPUT")
    image_url: HttpUrl = Field(..., description="要分析的图像的公开URL", alias="INPUT_IMAGE_URL")
    # 允许在请求体中传递额外的模型参数
    model_kwargs: dict[str, Any] = Field({}, description="传递给模型的额外参数，如 'max_tokens'")
    polling: bool = False

class AudioRequest(BaseModel):
    """音频转写请求的模型"""
    audio_url: HttpUrl = Field(..., description="要转写的音频文件的公开URL", alias="INPUT_AUDIO_URL")
    # VVVV 这里是核心修改 VVVV
    options: TranscriptionOptions = Field(default_factory=TranscriptionOptions, description="传递给火山引擎的详细转写选项")
    # ^^^^ 这里是核心修改 ^^^^
    polling: bool = False

class McpRequest(BaseModel):
    """MCP Agent 请求的模型"""
    prompt: str = Field(..., description="要交给 MCP Agent 处理的指令", alias="INPUT")
    polling: bool = False

# VVVV  在这里添加新的模型 VVVV
class DocumentAnalysisRequest(BaseModel):
    """文档图片分析请求的模型 (用于JSON请求体)"""
    file_url: HttpUrl = Field(..., description="要分析的文档的公开URL")
    polling: bool = Field(True, description="是否使用轮询模式")

# VVVV  在这里添加新的统一请求模型 VVVV
class UnifiedProcessingRequest(BaseModel):
    """
    统一处理接口的请求模型，能根据文件类型自动分发任务。
    """
    INPUT: str | None = Field(None, description="可选的文本输入，主要用于图像分析任务的提示词。")
    file_url: HttpUrl = Field(..., description="要处理的文件的公开URL (支持音频、图片、文档、文本等)。")
    model_kwargs: dict[str, Any] = Field(default_factory=dict, description="传递给底层模型的额外参数。")
    polling: bool = Field(True, description="是否使用轮询模式，默认为True。")

# --- API 输出模型 ---
# ... (已有代码保持不变) ...
# --- API 输出模型 ---

class FinalOutput(BaseModel):
    """直接返回结果时的标准输出模型"""
    output: Any