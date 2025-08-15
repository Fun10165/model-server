# src/app/services/task_manager.py
import uuid
import time
import logging
from threading import Lock, Timer
from typing import Dict, Any, Callable
from ..config import settings

# --- 任务状态常量 ---
class TaskStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# --- 内存中的任务存储 ---
# 使用线程锁来保证并发访问的安全性
_task_storage: Dict[str, Dict[str, Any]] = {}
_task_lock = Lock()

def create_task() -> str:
    """创建一个新任务，返回其唯一ID"""
    task_id = str(uuid.uuid4())
    with _task_lock:
        _task_storage[task_id] = {"status": TaskStatus.PENDING, "result": None, "error": None}
    logging.info(f"已创建新任务: {task_id}")
    return task_id

def get_task(task_id: str) -> Dict[str, Any] | None:
    """获取任务信息"""
    with _task_lock:
        return _task_storage.get(task_id)

def remove_task(task_id: str):
    """当任务完成后，从存储中移除以释放内存"""
    with _task_lock:
        if task_id in _task_storage:
            del _task_storage[task_id]
            logging.info(f"已按计划清理缓存的任务结果: {task_id}")

# VVVV 核心修改：添加新的调度函数 VVVV
def schedule_task_cleanup(task_id: str, delay_seconds: int):
    """
    创建一个计时器，在指定的秒数后调用 remove_task。
    这是一个非阻塞操作。
    """
    # 1. 创建一个 Timer 对象
    # 它会在 delay_seconds 秒后，在新的线程中执行 remove_task(task_id)
    cleanup_timer = Timer(delay_seconds, remove_task, args=[task_id])

    # 2. 将计时器线程设置为守护线程
    # 这意味着如果主程序退出，这个计时器线程不会阻止程序的关闭
    cleanup_timer.daemon = True
    
    # 3. 启动计时器
    cleanup_timer.start()
    
    logging.info(f"任务 {task_id} 的结果将缓存 {delay_seconds} 秒后自动清理。")
# ^^^^ 核心修改 ^^^^


def run_task_in_background(task_id: str, target_func: Callable, *args, **kwargs):
    """
    在后台执行一个目标函数，并包含自动重试逻辑。
    这是旧 server.py 中 task_executor 的重构版本。
    """
    try:
        with _task_lock:
            _task_storage[task_id]["status"] = TaskStatus.PROCESSING
        logging.info(f"任务 {task_id} 开始执行...")

        for attempt in range(settings.TASK_MAX_RETRIES):
            try:
                # 运行实际的任务函数
                result = target_func(*args, **kwargs)
                
                # 任务成功
                with _task_lock:
                    _task_storage[task_id]['status'] = TaskStatus.COMPLETED
                    _task_storage[task_id]['result'] = result
                logging.info(f"任务 {task_id} 在尝试 {attempt + 1} 次后成功完成。")
                return # 成功，退出函数

            except Exception as e:
                is_last_attempt = (attempt == settings.TASK_MAX_RETRIES - 1)
                logging.error(f"任务 {task_id} 尝试第 {attempt + 1}/{settings.TASK_MAX_RETRIES} 次失败: {e}", exc_info=is_last_attempt)
                
                if not is_last_attempt:
                    time.sleep(settings.TASK_RETRY_DELAY)
                else:
                    # 达到最大重试次数，将任务标记为最终失败
                    with _task_lock:
                        _task_storage[task_id]['status'] = TaskStatus.FAILED
                        _task_storage[task_id]['error'] = str(e)
                    return # 失败，退出函数
    except Exception as e:
        # 捕获 run_task_in_background 本身的意外错误
        logging.critical(f"执行任务 {task_id} 的后台处理器发生致命错误: {e}", exc_info=True)
        with _task_lock:
            _task_storage[task_id]['status'] = TaskStatus.FAILED
            _task_storage[task_id]['error'] = "任务执行器发生致命内部错误。"