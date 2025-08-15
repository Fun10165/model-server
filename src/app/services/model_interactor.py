# src/app/services/model_interactor.py
import base64
import io
import logging
from typing import List, Optional
import requests
from PIL import Image
from openai import OpenAI

from ..config import settings

class ModelProcessingError(Exception):
    """自定义模型处理异常"""
    pass

def _resize_image(image_data: bytes, max_dimension: int = 1024) -> tuple[bytes, str]:
    """调整图片大小，同时保持其宽高比。"""
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            if img.width <= max_dimension and img.height <= max_dimension:
                mime_type = Image.MIME.get(img.format)
                return image_data, mime_type

            if img.width > img.height:
                new_width = max_dimension
                new_height = int(max_dimension * img.height / img.width)
            else:
                new_height = max_dimension
                new_width = int(max_dimension * img.width / img.height)
            
            logging.info(f"图片尺寸过大 ({img.width}x{img.height})，正在缩放至 ({new_width}x{new_height})...")
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            output_buffer = io.BytesIO()
            image_format = img.format or 'JPEG' 
            resized_img.save(output_buffer, format=image_format)
            
            mime_type = Image.MIME.get(image_format)
            return output_buffer.getvalue(), mime_type
    except Exception as e:
        raise ModelProcessingError(f"图片缩放失败: {e}") from e


# VVVV 用这个新版本替换旧的 _encode_image_bytes VVVV
def _encode_image_bytes(image_data: bytes, min_dimension: int = 14) -> Optional[str]:
    """
    将二进制图片数据缩放并编码为 Base64 Data URL。
    新增：在处理前检查图片尺寸，过滤掉太小的图片。
    """
    try:
        # --- 核心修改：在这里进行尺寸校验 ---
        with Image.open(io.BytesIO(image_data)) as img:
            if img.width < min_dimension or img.height < min_dimension:
                logging.warning(f"跳过图片，因为其尺寸 ({img.width}x{img.height}) 过小。最小要求: {min_dimension}px。")
                return None # 返回 None 表示此图片无效，应被跳过
        # --- 修改结束 ---

        logging.info("正在处理二进制图片数据...")
        resized_image_data, mime_type = _resize_image(image_data)
        logging.info("图片处理完成，正在进行 Base64 编码...")
        base64_encoded_string = base64.b64encode(resized_image_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_encoded_string}"
    except Exception as e:
        # 如果图片本身已损坏无法打开，也当作无效图片处理
        logging.error(f"处理图片时发生错误，将跳过此图: {e}")
        return None
"""
def _download_and_encode_image(url: str) -> str:
    从 URL 下载图片，缩放，并编码为 Base64 Data URL。
    try:
        headers = {'User-Agent': 'MyAnalysisServer/1.0'}
        logging.info(f"正在从 URL 下载图片: {url}")
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        response.raise_for_status()
        
        original_image_data = response.content
        logging.info("图片下载成功，正在处理...")
        
        resized_image_data, mime_type = _resize_image(original_image_data)
        
        logging.info("图片处理完成，正在进行 Base64 编码...")
        base64_encoded_string = base64.b64encode(resized_image_data).decode("utf-8")
        
        return f"data:{mime_type};base64,{base64_encoded_string}"
    except requests.exceptions.RequestException as e:
        raise ModelProcessingError(f"下载图片失败，URL: {url}") from e
    except Exception as e:
        # 这会捕获 _resize_image 抛出的 ModelProcessingError
        raise ModelProcessingError(f"处理图片时发生错误: {e}") from e
"""
# VVVV  核心修改：函数现在接受一个图片列表 VVVV
def get_model_response(prompt: str, image_bytes_list: List[bytes] = None, **kwargs) -> str:
    """
    主函数，处理文本和一系列二进制图片，并获取模型响应。
    """
    final_api_key = kwargs.get('api_key') or settings.OPENAI_API_KEY
    final_base_url = kwargs.get('base_url') or settings.OPENAI_API_BASE_URL
    final_model = kwargs.get('model') or settings.MODEL_NAME

    if not final_api_key or not final_base_url:
        raise ModelProcessingError("API 密钥或基地址未在服务器上配置。")

    try:
        content = [{"type": "text", "text": prompt}]
        
        valid_image_urls = []
        if image_bytes_list:
            for img_bytes in image_bytes_list:
                # base64_image_url 现在可能是 str 或 None
                base64_image_url = _encode_image_bytes(img_bytes)
                if base64_image_url:
                    valid_image_urls.append(base64_image_url)

        for url in valid_image_urls:
            content.append(
                {"type": "image_url", "image_url": {"url": url}}
            )
        
        # 如果所有图片都被过滤掉了，打印一条日志
        if image_bytes_list and not valid_image_urls:
            logging.warning("警告：此批次的所有图片都因尺寸过小或格式错误而被跳过。")
            # 如果不希望在这种情况下调用模型，可以在这里直接返回一个提示信息
            # return "文档单元中的所有图片都无效，无法进行分析。"

        logging.info(f"向模型 '{final_model}' 发送请求，包含 {len(valid_image_urls)} 张有效图片。")
        
        client = OpenAI(api_key=final_api_key, base_url=final_base_url)
        response = client.chat.completions.create(
            model=final_model,
            messages=[{"role": "user", "content": content}],
            max_tokens=kwargs.get('max_tokens', 4096),
        )
        logging.info("成功获得模型返回结果。")
        return response.choices[0].message.content

    except ModelProcessingError as e:
        raise e
    except Exception as e:
        logging.error(f"调用模型API时发生未知错误: {e}", exc_info=True)
        raise ModelProcessingError(f"调用模型API时发生严重错误: {e}") from e