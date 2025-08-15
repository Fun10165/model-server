# --- START OF FILE audio_utils.py ---

import os
import uuid
import logging
import requests
import subprocess
from urllib.parse import urlparse

# 从中央配置导入设置
from ..config import settings

class AudioProcessingError(Exception):
    """自定义音频处理异常"""
    pass

def ensure_audio_is_compatible(audio_url: str, server_base_url: str) -> tuple[str, str, str]:
    """
    检查音频格式，如果不兼容则使用FFmpeg下载并转换为MP3。

    Args:
        audio_url: 原始音频文件的URL。
        server_base_url: 本服务器的公网访问地址。

    Returns:
        元组 (new_url, converted_path, original_path)。
        - new_url: 最终可供API访问的MP3文件URL。
        - converted_path: 转换后文件的本地路径 (如果进行了转换)。
        - original_path: 下载的原始文件的本地路径 (如果进行了转换)。

    Raises:
        AudioProcessingError: 如果下载或转换失败。
    """
    parsed_url = urlparse(audio_url)
    file_extension = os.path.splitext(parsed_url.path)[1].lower()

    if file_extension in settings.COMPATIBLE_AUDIO_FORMATS:
        logging.info(f"音频格式 {file_extension} 兼容，无需转换。")
        return audio_url, None, None

    logging.warning(f"音频格式 {file_extension} 不兼容，将尝试使用FFmpeg转换为MP3。")
    
    unique_id = uuid.uuid4()
    original_filename = f"{unique_id}{file_extension}"
    converted_filename = f"{unique_id}.mp3"
    original_filepath = os.path.join(settings.TEMP_DIR, original_filename)
    converted_filepath = os.path.join(settings.FILES_DIR, converted_filename)

    try:
        logging.info(f"正在从 {audio_url} 下载文件到 {original_filepath}")
        with requests.get(audio_url, stream=True, timeout=settings.DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            with open(original_filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        logging.info(f"正在将 {original_filepath} 转换为 {converted_filepath}")
        command = [
            'ffmpeg', '-i', original_filepath, '-vn',
            '-acodec', 'libmp3lame', '-q:a', '2', '-y',
            converted_filepath
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=settings.FFMPEG_TIMEOUT)
        logging.info("FFmpeg转换成功。")

        new_public_url = f"{server_base_url}/files/{converted_filename}"
        logging.info(f"转换后的文件可通过URL访问: {new_public_url}")
        
        return new_public_url, converted_filepath, original_filepath

    except requests.RequestException as e:
        raise AudioProcessingError(f"下载音频文件失败: {e}") from e
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg执行失败！\n--- STDERR ---\n{e.stderr}")
        raise AudioProcessingError("FFmpeg转换音频失败。") from e
    except subprocess.TimeoutExpired:
        raise AudioProcessingError("音频转换任务超时。")
    except Exception as e:
        logging.error(f"处理音频时发生未知错误: {e}", exc_info=True)
        raise AudioProcessingError(f"未知的音频处理错误: {e}")
    
def cleanup_temp_files(converted_path: str | None, original_path: str | None):
    """清理在处理过程中产生的临时文件"""
    for path in [converted_path, original_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logging.info(f"已清理临时文件: {path}")
            except OSError as e:
                logging.error(f"清理临时文件失败: {path}, 错误: {e}")