# src/app/services/aippt_client.py
import hashlib
import hmac
import base64
import json
import time
import logging
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from typing import IO, Tuple

from ..config import settings

class AipptProcessingError(Exception):
    """自定义AIPPT处理异常"""
    pass

# _md5, _hmac_sha1_encrypt, _get_signature 函数保持不变
def _md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def _hmac_sha1_encrypt(encrypt_text: str, encrypt_key: str) -> str:
    return base64.b64encode(hmac.new(encrypt_key.encode('utf-8'), encrypt_text.encode('utf-8'), hashlib.sha1).digest()).decode('utf-8')

def _get_signature(app_id: str, api_secret: str, ts: int) -> str:
    auth = _md5(app_id + str(ts))
    return _hmac_sha1_encrypt(auth, api_secret)


# VVVV  核心修改：重构 _create_task 函数 VVVV
def _create_task(options: dict, query: str = None, file_content: IO[bytes] = None, file_name: str = None) -> tuple[str, dict]:
    """
    提交PPT生成任务到讯飞服务器。
    支持三种输入源：query, file_content, 或 fileUrl (在options中提供)。
    """
    url = 'https://zwapi.xfyun.cn/api/ppt/v2/create'
    timestamp = int(time.time())
    
    signature = _get_signature(settings.XF_AIPPT_APP_ID, settings.XF_AIPPT_API_SECRET, timestamp)
    
    # 准备表单字段
    fields = options.copy()
    if query:
        fields['query'] = query
    
    # 如果有文件内容，将其添加到表单中
    if file_content and file_name:
        fields['file'] = (file_name, file_content, 'application/octet-stream')
        fields['fileName'] = file_name
    elif options.get('fileUrl') and 'fileName' in options:
        # 如果提供了 fileUrl，确保 fileName 也存在
        pass # fileName 已经在 options 中了
    
    # 将布尔值转换为讯飞API要求的字符串形式
    for key in ['isCardNote', 'search', 'isFigure']:
        if key in fields and isinstance(fields[key], bool):
            fields[key] = str(fields[key])

    form_data = MultipartEncoder(fields=fields)
    
    headers = {
        "appId": settings.XF_AIPPT_APP_ID,
        "timestamp": str(timestamp),
        "signature": signature,
        "Content-Type": form_data.content_type
    }

    logging.info("正在向讯飞提交AIPPT创建任务...")
    logging.debug(f"提交的表单字段: {fields.keys()}")
    
    response = requests.post(url, data=form_data, headers=headers, timeout=60) # 增加超时时间
    response.raise_for_status()
    resp_json = response.json()
    
    logging.info(f"讯飞AIPPT任务创建响应: {resp_json}")
    if resp_json.get('code') == 0:
        return resp_json['data']['sid'], headers
    else:
        raise AipptProcessingError(f"创建PPT任务失败: {resp_json.get('desc', '未知错误')}")

def _poll_progress(sid: str, headers: dict) -> dict:
    """轮询任务进度"""
    url = f"https://zwapi.xfyun.cn/api/ppt/v2/progress?sid={sid}"
    # 移除 Content-Type，因为GET请求没有body
    polling_headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}

    response = requests.get(url, headers=polling_headers, timeout=10)
    response.raise_for_status()
    return response.json()

# VVVV 核心修改：重构主流程函数 VVVV
def generate_ppt(options: dict, query: str = None, file_content: IO[bytes] = None, file_name: str = None) -> str:
    """
    通用的主流程函数，处理所有类型的PPT生成请求。
    """
    if not settings.XF_AIPPT_APP_ID or not settings.XF_AIPPT_API_SECRET:
        raise AipptProcessingError("服务器未配置讯飞AIPPT的APP_ID或API_SECRET。")

    # 根据输入源调用 _create_task
    sid, headers = _create_task(options, query=query, file_content=file_content, file_name=file_name)
    
    logging.info(f"讯飞任务ID (sid): {sid}，开始轮询进度...")
    
    start_time = time.time()
    while time.time() - start_time < 600: # 添加一个10分钟的超时，防止无限循环
        try:
            progress_resp = _poll_progress(sid, headers)
            if progress_resp.get('code') != 0:
                raise AipptProcessingError(f"查询进度失败: {progress_resp.get('desc')}")

            data = progress_resp.get('data', {})
            ppt_status = data.get('pptStatus', 'building')
            ai_image_status = data.get('aiImageStatus', 'building')
            card_note_status = data.get('cardNoteStatus', 'building')

            logging.info(f"轮询 sid: {sid}, ppt: {ppt_status}, image: {ai_image_status}, note: {card_note_status}")

            if ppt_status == 'done' and ai_image_status == 'done' and card_note_status == 'done':
                ppt_url = data.get('pptUrl')
                if ppt_url:
                    logging.info(f"PPT生成成功！URL: {ppt_url}")
                    return ppt_url
                else:
                    raise AipptProcessingError("任务显示完成，但未找到pptUrl。")
            
            if ppt_status == 'build_failed' or ai_image_status == 'build_failed' or card_note_status == 'build_failed':
                 raise AipptProcessingError("PPT生成过程中某个子任务失败。")
            
            time.sleep(5) # 每次轮询后等待5秒，避免过于频繁

        except requests.RequestException as e:
            logging.error(f"轮询AIPPT任务进度时发生网络错误: {e}")
            time.sleep(5) # 网络错误后也等待
        except Exception as e:
            # 捕获所有其他异常并终止
            logging.error(f"处理AIPPT任务时发生未知错误: {e}", exc_info=True)
            raise AipptProcessingError(f"处理任务时发生未知错误: {e}")
    raise AipptProcessingError("PPT生成超时（超过10分钟）。") # 添加超时错误