# src/app/utils/download_util.py

import os
import uuid
import logging
import requests
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 从中央配置导入设置
from ..config import settings

class DownloadError(Exception):
    """自定义下载异常"""
    pass

# VVVV  用下面的新函数完全替换旧的 download_file 函数 VVVV
def download_file(url: str, connect_timeout: int = 10, read_timeout: int = 60) -> tuple[str, str]:
    """
    通用的文件下载工具，内置了健壮的重试逻辑。
    它从 URL 下载文件并将其保存到临时目录。

    Args:
        url (str): 要下载的文件的URL。
        connect_timeout (int): 建立连接的超时时间（秒）。
        read_timeout (int): 等待服务器发送数据的超时时间（秒）。

    Returns:
        tuple[str, str]: (本地文件路径, 原始文件名)
    """
    logging.info(f"通用下载工具: 准备从 {url} 下载文件...")

    # --- 核心修改：配置带有重试策略的会话 ---
    session = requests.Session()
    retry_strategy = Retry(
        total=3,  # 总共重试3次
        backoff_factor=1,  # 重试间的等待时间会指数增长 (e.g., 0s, 2s, 4s)
        status_forcelist=[429, 500, 502, 503, 504],  # 对这些服务器错误状态码进行重试
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # --- 修改结束 ---
    
    try:
        # 1. 从 URL 解析原始文件名
        parsed_url = urlparse(url)
        original_filename = os.path.basename(parsed_url.path)
        if not original_filename:
            _, extension = os.path.splitext(parsed_url.path)
            original_filename = f"downloaded_file{extension or '.tmp'}"

        # 2. 创建一个唯一的本地文件路径
        unique_id = uuid.uuid4()
        local_filename = f"{unique_id}_{original_filename}"
        local_filepath = os.path.join(settings.TEMP_DIR, local_filename)
        os.makedirs(settings.TEMP_DIR, exist_ok=True)

        # 3. 执行下载 (使用配置好的会话和更精细的超时元组)
        headers = {'User-Agent': 'Model-Server-Downloader/1.0'}
        # 使用 session.get 替代 requests.get
        with session.get(url, headers=headers, stream=True, timeout=(connect_timeout, read_timeout)) as r:
            r.raise_for_status()
            with open(local_filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        logging.info(f"文件已成功下载到临时路径: {local_filepath}")
        return local_filepath, original_filename

    except requests.exceptions.RequestException as e:
        logging.error(f"下载文件时发生网络或HTTP错误: {e}", exc_info=True)
        raise DownloadError(f"下载文件失败: {e}") from e
    except Exception as e:
        logging.error(f"下载文件时发生未知错误: {e}", exc_info=True)
        raise DownloadError(f"下载时发生未知错误: {e}")

def cleanup_temp_file(filepath: str):
    """安全地清理单个临时文件。"""
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
            logging.info(f"已清理临时文件: {filepath}")
        except OSError as e:
            logging.error(f"清理临时文件失败: {filepath}, 错误: {e}")
