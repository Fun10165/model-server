# src/app/services/volc_client.py
import json
import time
import uuid
import logging
import requests

from ..config import settings

class TranscriptionError(Exception):
    """自定义语音识别任务异常"""
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details

def run_transcription(file_url: str, options: dict) -> dict:
    """
    提交并轮询火山语音大模型任务。
    Args:
        file_url (str): 公网可访问的音频文件URL。
        options (dict): 一个包含所有可选功能参数的字典。
    """
    if not settings.VOLC_APPID or not settings.VOLC_TOKEN:
        raise TranscriptionError("服务器未配置火山引擎APPID或TOKEN。")

    task_id, x_tt_logid = _submit_task(file_url, options)
    result = _poll_for_result(task_id, x_tt_logid)
    return result

def _submit_task(file_url: str, options: dict) -> tuple[str, str]:
    task_id = str(uuid.uuid4())
    headers = {
        "X-Api-App-Key": settings.VOLC_APPID,
        "X-Api-Access-Key": settings.VOLC_TOKEN,
        "X-Api-Resource-Id": "volc.bigasr.auc",
        "X-Api-Request-Id": task_id,
        "X-Api-Sequence": "-1"
    }
    
    # --- 核心修改：动态构建请求参数 ---
    # 我们将从 options 字典中获取所有已知参数
    request_params = {
        "model_name": "bigmodel", # 固定值
    }
    # 将 options 字典中的所有键值对都添加到 request_params 中
    request_params.update(options)
    # --- 修改结束 ---

    request_payload = {
        "user": {"uid": "generic_user_for_server"},
        "audio": {"url": file_url},
        "request": request_params # 使用我们动态构建的参数
    }

    logging.info(f"向火山引擎提交语音识别任务，任务ID: {task_id}")
    logging.debug(f"提交的请求体: {json.dumps(request_payload)}") # 使用 debug 级别记录详细信息

    try:
        response = requests.post(settings.VOLC_SUBMIT_URL, data=json.dumps(request_payload), headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise TranscriptionError("提交任务时发生网络错误", details=str(e))

    if response.headers.get("X-Api-Status-Code") == "20000000":
        logid = response.headers.get("X-Tt-Logid", "")
        logging.info(f"任务提交成功。Log ID: {logid}")
        return task_id, logid
    else:
        raise TranscriptionError("提交任务失败", details=response.text)

def _poll_for_result(task_id: str, x_tt_logid: str) -> dict:
    # _poll_for_result 函数无需修改，保持原样
    headers = {
        "X-Api-App-Key": settings.VOLC_APPID,
        "X-Api-Access-Key": settings.VOLC_TOKEN,
        "X-Api-Resource-Id": "volc.bigasr.auc",
        "X-Api-Request-Id": task_id,
    }
    current_sleep_time = settings.QUERY_INITIAL_SLEEP
    while True:
        headers["X-Tt-Logid"] = x_tt_logid
        logging.info(f"查询任务状态，任务ID: {task_id}")
        try:
            query_response = requests.post(settings.VOLC_QUERY_URL, data=json.dumps({}), headers=headers, timeout=10)
            query_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise TranscriptionError("查询任务时发生网络错误", details=str(e))
        x_tt_logid = query_response.headers.get('X-Tt-Logid', x_tt_logid)
        code = query_response.headers.get('X-Api-Status-Code', "")
        if code == '20000000':
            logging.info(f"任务成功完成。Log ID: {x_tt_logid}")
            return query_response.json()
        elif code in ('20000001', '20000002'):
            msg = query_response.headers.get('X-Api-Message', 'In progress')
            logging.info(f"任务进行中 ({msg})... 将在 {current_sleep_time:.1f} 秒后重试。")
            time.sleep(current_sleep_time)
            current_sleep_time = min(current_sleep_time * settings.QUERY_FACTOR, settings.QUERY_MAX_SLEEP)
        else:
            raise TranscriptionError("语音识别任务失败", details=query_response.text)