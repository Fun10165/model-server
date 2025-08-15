# src/app/schemas/volc.py
from pydantic import BaseModel, Field

class TranscriptionOptions(BaseModel):
    """
    定义所有可传递给火山引擎的音频转写参数。
    这些参数会直接显示在API文档中，方便用户查阅和使用。
    """
    model_version: str = Field("400", description='模型版本, "400"为增强版, "310"为基础版')
    enable_itn: bool = Field(False, description="开启文本逆规范化 (e.g., '一百二十三' -> '123')")
    enable_punc: bool = Field(True, description="开启自动加标点") # 默认开启，更常用
    enable_ddc: bool = Field(False, description="开启语义顺滑，移除停顿词、语气词等")
    enable_speaker_info: bool = Field(True, description="开启说话人分离") # 默认开启，更常用
    enable_channel_split: bool = Field(False, description="开启双声道识别")
    show_utterances: bool = Field(True, description="输出分句、分词等详细信息")
    show_speech_rate: bool = Field(True, description="分句信息携带语速 (依赖show_utterances)")
    show_volume: bool = Field(True, description="分句信息携带音量 (依赖show_utterances)")
    enable_lid: bool = Field(True, description="开启语种识别")
    enable_emotion_detection: bool = Field(True, description="开启情绪检测")
    enable_gender_detection: bool = Field(True, description="开启性别检测")
    vad_segment: bool = Field(False, description="使用VAD分句（默认为语义分句）")

    class Config:
        # 允许在请求中只提供部分字段，未提供的将使用默认值
        extra = 'ignore'