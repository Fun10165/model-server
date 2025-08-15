# src/app/api/router.py
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, File, UploadFile, Form, Request
from typing import Union, Annotated # Annotated 是一个新特性，用于更好地组织依赖项
import os
from urllib.parse import urlparse
from fastapi.concurrency import run_in_threadpool # <--- 导入这个模块
from ..schemas import tasks as task_schemas, aippt as aippt_schemas
from ..services import (
    model_interactor, 
    audio_processor, 
    volc_client, 
    mcp_agent_manager,
    task_manager,
    aippt_client,
    document_parser,
)
from ..utils import download_util 
from ..utils.response_parser import parse_transcription_output # 我们将在下一步创建它

router = APIRouter(prefix="/api/v1")

# --- 核心任务轮询端点 ---
# src/app/api/router.py

# ... (其他导入)

@router.get("/tasks/{task_id}", 
            response_model=task_schemas.TaskStatusResponse, 
            tags=["Task Management"],
            summary="查询异步任务的状态")
def get_task_status(task_id: str):
    """根据任务ID获取任务的当前状态、结果或错误。"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务ID不存在或已过期")

    status = task['status']
    response_data = {"task_id": task_id, "status": status, "result": task.get('result')}
    
    # VVVV  这里是核心修改 VVVV
    if status == task_manager.TaskStatus.COMPLETED:
        # 不再立即删除，而是安排在一小时后删除
        task_manager.schedule_task_cleanup(task_id, delay_seconds=3600)
        return response_data
    elif status == task_manager.TaskStatus.FAILED:
        response_data['result'] = {"error": task.get('error', '未知错误')}
        # 失败的任务也安排在一小时后删除
        task_manager.schedule_task_cleanup(task_id, delay_seconds=3600)
        return response_data
    # ^^^^  核心修改 ^^^^
    else: # PENDING or PROCESSING
        return response_data

# VVVV 用这个新版本完全替换旧的 analyze_image 函数 VVVV
@router.post("/vision/analyze",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["AI Services"],
             summary="处理图像和文本输入")
async def analyze_image(request: task_schemas.VisionRequest, background_tasks: BackgroundTasks):
    """
    接收图像URL和文本提示，返回模型分析结果。
    """
    def perform_vision_analysis(prompt: str, image_url: str, model_kwargs: dict):
        local_image_path = None
        try:
            logging.info(f"开始执行 Vision Analysis 任务，URL: {image_url}")
            local_image_path, _ = download_util.download_file(image_url)
            
            with open(local_image_path, 'rb') as f:
                image_content = f.read()

            return model_interactor.get_model_response(
                prompt=prompt,
                image_bytes_list=[image_content],
                **model_kwargs
            )
        # ++++ 核心修改：捕获更广泛的异常并提供详细日志 ++++
        except Exception as e:
            # 记录详细的错误信息和堆栈跟踪，这对于调试至关重要！
            logging.error(f"在 perform_vision_analysis 中发生严重错误: {e}", exc_info=True)
            # 重新抛出异常，让 run_task_in_background 或上层调用者能够捕获它
            raise e
        finally:
            if local_image_path:
                download_util.cleanup_temp_file(local_image_path)

    if not request.polling:
        try:
            # 直接调用
            result = perform_vision_analysis(
                request.prompt, str(request.image_url), request.model_kwargs
            )
            return task_schemas.FinalOutput(output=result)
        # ++++ 核心修改：在API层也捕获所有异常 ++++
        except Exception as e:
            # 将任何在执行过程中发生的错误，都包装成一个清晰的 HTTP 500 响应
            raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
    else:
        task_id = task_manager.create_task()
        background_tasks.add_task(
            task_manager.run_task_in_background,
            task_id, 
            perform_vision_analysis,
            request.prompt,
            str(request.image_url),
            request.model_kwargs
        )
        return task_schemas.TaskCreationResponse(task_id=task_id)
# ... (其他导入和路由)

@router.post("/audio/transcribe",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["AI Services"],
             summary="转写音频文件")
async def transcribe_audio(http_request: Request, audio_request: task_schemas.AudioRequest, background_tasks: BackgroundTasks):
    """
    接收音频URL，返回转写结果。支持自动格式转换和失败重试。
    """
    def perform_transcription(url: str, opts: task_schemas.TranscriptionOptions):
        server_base_url = str(http_request.base_url)
        processed_url, converted_path, original_path = audio_processor.ensure_audio_is_compatible(
            url, server_base_url
        )
        try:
            # VVVV 核心修改：使用 .model_dump() 将 Pydantic 模型转为字典 VVVV
            raw_result = volc_client.run_transcription(processed_url, opts.model_dump())
            # ^^^^ 核心修改 ^^^^
            return parse_transcription_output(raw_result)
        finally:
            audio_processor.cleanup_temp_files(converted_path, original_path)

    if not audio_request.polling:
        try:
            # VVVV 核心修改 VVVV
            # 将阻塞函数放入线程池执行，避免阻塞事件循环
            result = await run_in_threadpool(
                perform_transcription, 
                str(audio_request.audio_url), 
                audio_request.options
            )
            # ^^^^ 核心修改 ^^^^
            return task_schemas.FinalOutput(output=result)
        except (audio_processor.AudioProcessingError, volc_client.TranscriptionError) as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # ... (轮询逻辑保持不变)
        task_id = task_manager.create_task()
        background_tasks.add_task(
            task_manager.run_task_in_background,
            task_id, perform_transcription, str(audio_request.audio_url), audio_request.options
        )
        return task_schemas.TaskCreationResponse(task_id=task_id)

# ... (其他路由)
@router.post("/mcp/execute",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["AI Services"],
             summary="执行MCP Agent指令")
async def execute_mcp(request: task_schemas.McpRequest, background_tasks: BackgroundTasks):
    """将指令发送给 LangGraph Agent 执行。"""
    if not mcp_agent_manager.is_agent_ready():
         raise HTTPException(status_code=503, detail="MCP Agent尚未准备就绪，请稍后再试。")

    async def perform_mcp_query(prompt: str):
        return await mcp_agent_manager.process_mcp_query(prompt)

    if not request.polling:
        try:
            result = await perform_mcp_query(request.prompt)
            return task_schemas.FinalOutput(output=result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"MCP Agent 执行失败: {e}")
    else:
        task_id = task_manager.create_task()
        # 注意：对于async函数，我们直接将其传递给add_task
        # run_task_in_background 内部会处理 await
        async def task_wrapper():
            # 创建一个包装器以适应 run_task_in_background 的同步接口
            try:
                result = await perform_mcp_query(request.prompt)
                with task_manager._task_lock:
                    task_manager._task_storage[task_id]['status'] = task_manager.TaskStatus.COMPLETED
                    task_manager._task_storage[task_id]['result'] = result
            except Exception as e:
                with task_manager._task_lock:
                    task_manager._task_storage[task_id]['status'] = task_manager.TaskStatus.FAILED
                    task_manager._task_storage[task_id]['error'] = str(e)

        # 由于MCP agent的执行是异步的，且已有自己的异常处理，我们直接用background_tasks
        # 注意：这里的重试逻辑需要由 process_mcp_query 内部实现，或调整 task_manager 以支持 async
        # 为简单起见，我们暂时直接调用，不经过重试逻辑
        background_tasks.add_task(task_wrapper)
        return task_schemas.TaskCreationResponse(task_id=task_id)
    
# VVVV 用下面的新函数完全替换旧的 generate_ppt VVVV
@router.post("/ppt/generate/from-text",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["AI PPT Services"],
             summary="通过文本直接生成PPT")
async def generate_ppt_from_text(
    request: aippt_schemas.AipptTextRequest, 
    background_tasks: BackgroundTasks
):
    """
    接收一个JSON请求体，包含文本主题和相关选项，异步生成PPT。
    """
    options_dict = request.options.model_dump()

    if not request.polling:
        try:
            # VVVV 核心修改 VVVV
            result_url = await run_in_threadpool(
                aippt_client.generate_ppt, 
                options=options_dict, 
                query=request.query
            )
            # ^^^^ 核心修改 ^^^^
            return task_schemas.FinalOutput(output=result_url)
        except aippt_client.AipptProcessingError as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # ... (轮询逻辑保持不变)
        task_id = task_manager.create_task()
        background_tasks.add_task(
            task_manager.run_task_in_background,
            task_id, aippt_client.generate_ppt, options=options_dict, query=request.query
        )
        return task_schemas.TaskCreationResponse(task_id=task_id)


# VVVV  用下面的新函数完全替换旧的 generate_ppt_from_file VVVV
@router.post("/ppt/generate/from-file",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["AI PPT Services"],
             summary="通过文档URL生成PPT (JSON接口)")
async def generate_ppt_from_file(
    request: aippt_schemas.AipptFileRequest, # <--- 核心改动：接收新的JSON模型
    background_tasks: BackgroundTasks
):
    """
    接收一个包含文档URL的JSON，异步生成PPT。
    此版本为适配仅支持application/json的Agent平台。
    """
    options_dict = request.options.model_dump()

    # 创建一个健壮的包装函数，处理下载、处理和清理的完整流程
    def perform_ppt_generation_from_url(url: str, query_str: str | None, opts: dict):
        local_file_path = None
        try:
            logging.info(f"PPT生成任务：正在从URL下载文件。 URL: {url}")
            local_file_path, filename = download_util.download_file(url)
            logging.info(f"文件下载成功: {filename}。准备提交给AIPPT服务。")
            
            with open(local_file_path, 'rb') as f:
                content = f.read()

            # 调用现有的、无需修改的服务层函数
            return aippt_client.generate_ppt(
                options=opts,
                query=query_str,
                file_content=content,
                file_name=filename
            )
        except Exception as e:
            logging.error(f"从URL生成PPT时发生严重错误: {e}", exc_info=True)
            raise e # 重新抛出，让上层处理器捕获
        finally:
            if local_file_path:
                download_util.cleanup_temp_file(local_file_path)

    # --- 任务执行逻辑 ---
    if not request.polling:
        try:
            # 在线程池中运行阻塞的下载和处理任务
            result_url = await run_in_threadpool(
                perform_ppt_generation_from_url,
                str(request.file_url),
                request.query,
                options_dict
            )
            return task_schemas.FinalOutput(output=result_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
    else: # 轮询模式
        task_id = task_manager.create_task()
        background_tasks.add_task(
            task_manager.run_task_in_background,
            task_id,
            perform_ppt_generation_from_url,
            str(request.file_url),
            request.query,
            options_dict
        )
        return task_schemas.TaskCreationResponse(task_id=task_id)
    
# VVVV 用下面的新函数完全替换旧的 analyze_document_images VVVV
@router.post("/document/analyze-images",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["Document Services"],
             summary="通过文档URL解析并分析所有图片 (JSON接口)")
async def analyze_document_images(
    request: task_schemas.DocumentAnalysisRequest, # <--- 核心改动：接收新的JSON模型
    background_tasks: BackgroundTasks
):
    """
    接收一个包含文档URL的JSON，提取其中所有的图片，并结合相应文本进行并发分析。
    此版本为适配仅支持application/json的Agent平台。
    """
    target_func = document_parser.process_document_images

    # +++ 这个健壮的包装函数保持不变，非常有用 +++
    def task_wrapper_for_url(url: str):
        local_file_path = None
        try:
            logging.info(f"任务开始：正在从URL下载文件。 URL: {url}")
            local_file_path, filename = download_util.download_file(url)
            logging.info(f"文件下载成功: {filename}。准备进行解析。")
            with open(local_file_path, 'rb') as f:
                content = f.read()
            
            result = target_func(content, filename)
            logging.info(f"文档 '{filename}' 分析成功。")
            return result
        except Exception as e:
            logging.error(f"处理来自URL '{url}' 的文档时发生严重错误: {e}", exc_info=True)
            raise e
        finally:
            if local_file_path:
                download_util.cleanup_temp_file(local_file_path)

    # --- 核心改动：简化了主逻辑，不再处理文件上传 ---
    if not request.polling:
        try:
            # 对于URL的直接请求，我们在线程池中运行包装器
            result = await run_in_threadpool(task_wrapper_for_url, str(request.file_url))
            return task_schemas.FinalOutput(output=result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
    else: # 轮询模式
        task_id = task_manager.create_task()
        background_tasks.add_task(
            task_manager.run_task_in_background, 
            task_id, 
            task_wrapper_for_url, 
            str(request.file_url)
        )
        return task_schemas.TaskCreationResponse(task_id=task_id)
    
# VVVV  在这里添加全新的统一处理接口  VVVV

@router.post("/process/unified",
             response_model=Union[task_schemas.FinalOutput, task_schemas.TaskCreationResponse],
             tags=["Unified Services"],
             summary="统一处理接口，自动分发任务")
async def process_unified(
    request: task_schemas.UnifiedProcessingRequest,
    # 我们需要 http_request 来获取服务器的 base_url，用于音频转写后的文件URL生成
    http_request: Request, 
    background_tasks: BackgroundTasks
):
    """
    接收一个包含文件URL的统一请求，并根据文件类型自动分发到相应的服务。
    - **音频文件**: 分发到语音转写服务。
    - **图片文件**: 结合INPUT作为提示词，分发到视觉分析服务。
    - **文档文件 (docx, pptx, pdf, xlsx)**: 分发到文档图片分析服务。
    - **纯文本文件 (txt, md)**: 直接下载并返回其内容。
    """
    
    # --- 辅助函数定义区域 ---
    # 将每种逻辑封装起来，使主流程更清晰

    def _perform_unified_transcription(audio_url: str):
        """处理音频转写的完整流程"""
        server_base_url = str(http_request.base_url)
        processed_url, converted_path, original_path = audio_processor.ensure_audio_is_compatible(
            audio_url, server_base_url
        )
        try:
            # 假设 model_kwargs 可以直接传递给 volc_client
            # 如果需要特定字段，可以在这里做转换
            transcription_options = request.model_kwargs.get("options", {})
            raw_result = volc_client.run_transcription(processed_url, transcription_options)
            return parse_transcription_output(raw_result)
        finally:
            audio_processor.cleanup_temp_files(converted_path, original_path)

    def _perform_unified_image_analysis(image_url: str, prompt: str):
        """处理图片分析的完整流程"""
        local_image_path = None
        try:
            local_image_path, _ = download_util.download_file(image_url)
            with open(local_image_path, 'rb') as f:
                image_content = f.read()
            return model_interactor.get_model_response(
                prompt=prompt,
                image_bytes_list=[image_content],
                **request.model_kwargs
            )
        finally:
            if local_image_path:
                download_util.cleanup_temp_file(local_image_path)
    
    def _perform_unified_document_analysis(doc_url: str):
        """处理文档分析的完整流程"""
        local_file_path = None
        try:
            local_file_path, filename = download_util.download_file(doc_url)
            with open(local_file_path, 'rb') as f:
                content = f.read()
            # 注意：document_parser.process_document_images 是一个CPU密集型函数
            # 在非轮询模式下，它会自动被 run_in_threadpool 调用
            return document_parser.process_document_images(content, filename)
        finally:
            if local_file_path:
                download_util.cleanup_temp_file(local_file_path)

    def _perform_unified_text_retrieval(text_url: str):
        """处理纯文本文件读取的完整流程"""
        local_file_path = None
        try:
            local_file_path, _ = download_util.download_file(text_url)
            with open(local_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            # 如果读取失败，也尝试用二进制模式下载并返回错误信息
            logging.error(f"读取文本文件失败: {e}", exc_info=True)
            raise IOError(f"无法将文件作为UTF-8文本读取: {e}")
        finally:
            if local_file_path:
                download_util.cleanup_temp_file(local_file_path)

    # --- 任务调度器主逻辑 ---

    # 1. 从URL中解析出文件扩展名
    try:
        parsed_url = urlparse(str(request.file_url))
        filename = os.path.basename(parsed_url.path)
        file_ext = os.path.splitext(filename)[1].lower()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析提供的file_url: {e}")

    # 2. 根据文件扩展名确定要执行的目标函数和参数
    target_func = None
    args = []

    # 定义文件类型映射
    AUDIO_EXTS = ('.wav', '.mp3', '.ogg', '.m4a', '.flac')
    IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
    DOC_EXTS = ('.docx', '.pptx', '.pdf', '.xlsx')
    TEXT_EXTS = ('.txt', '.md', '.json', '.xml', '.csv')

    if file_ext in AUDIO_EXTS:
        target_func = _perform_unified_transcription
        args = [str(request.file_url)]
    elif file_ext in IMAGE_EXTS:
        if not request.INPUT:
            raise HTTPException(status_code=400, detail="处理图片文件时，必须提供'INPUT'字段作为提示词。")
        target_func = _perform_unified_image_analysis
        args = [str(request.file_url), request.INPUT]
    elif file_ext in DOC_EXTS:
        target_func = _perform_unified_document_analysis
        args = [str(request.file_url)]
    elif file_ext in TEXT_EXTS:
        target_func = _perform_unified_text_retrieval
        args = [str(request.file_url)]
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: '{file_ext}'。")

    # 3. 根据 polling 参数执行任务
    if not request.polling:
        try:
            # 对于IO或CPU密集型任务，使用 run_in_threadpool 避免阻塞事件循环
            result = await run_in_threadpool(target_func, *args)
            return task_schemas.FinalOutput(output=result)
        except Exception as e:
            logging.error(f"统一接口在直接执行模式下失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
    else: # 轮询模式
        task_id = task_manager.create_task()
        background_tasks.add_task(
            task_manager.run_task_in_background, 
            task_id, 
            target_func, 
            *args
        )
        return task_schemas.TaskCreationResponse(task_id=task_id)