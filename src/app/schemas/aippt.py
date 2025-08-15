# src/app/schemas/aippt.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal

class AipptOptions(BaseModel):
    """定义所有可传递给讯飞AIPPT服务的选项"""
    templateId: str = Field("20240718489569D", description="模板ID")
    author: str | None = Field("默认作者名", description="PPT作者名")
    isCardNote: bool = Field(True, description="是否生成PPT演讲备注")
    search: bool = Field(True, description="是否启用联网搜索")
    isFigure: bool = Field(True, description="是否自动配图")
    aiImage: Literal["normal", "advanced"] = Field("advanced", description="AI配图类型")
    language: Literal["cn", "en"] = Field("cn", description="生成PPT的语种")

class AipptTextRequest(BaseModel):
    """仅通过文本生成PPT的请求模型（用于JSON请求体）"""
    query: str = Field(..., description="生成PPT的核心要求或主题")
    options: AipptOptions = Field(default_factory=AipptOptions, description="PPT生成的详细选项")
    polling: bool = True

# VVVV  在这里添加新的模型 VVVV
class AipptFileRequest(BaseModel):
    """通过文档URL生成PPT的请求模型 (用于JSON请求体)"""
    file_url: HttpUrl = Field(..., description="用于生成PPT的文档的公开URL")
    query: str | None = Field(None, description="对文档的额外要求或主题概括，可选")
    options: AipptOptions = Field(default_factory=AipptOptions, description="PPT生成的详细选项")
    polling: bool = True