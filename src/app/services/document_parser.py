# src/app/services/document_parser.py
import io
import logging
from typing import List, Tuple, IO, TypedDict, Generator
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed


# 导入文档解析库
import docx
from pptx import Presentation
import openpyxl
import fitz  # PyMuPDF

# 导入我们已有的模型处理服务
from . import model_interactor

class DocumentParsingError(Exception):
    pass

class DocumentUnit(TypedDict):
    unit_identifier: str
    text: str
    images: List[bytes]

def _chunk_list(data: list, size: int) -> Generator[list, None, None]:
    """一个辅助函数，将列表分割成指定大小的块"""
    for i in range(0, len(data), size):
        yield data[i:i + size]

# --- 提取函数部分（无改动） ---

def _extract_from_pptx(file_stream: IO[bytes]) -> List[DocumentUnit]:
    presentation = Presentation(file_stream)
    units: List[DocumentUnit] = []
    for i, slide in enumerate(presentation.slides):
        slide_text = "\n".join([shape.text for shape in slide.shapes if shape.has_text_frame]).strip()
        images = [shape.image.blob for shape in slide.shapes if hasattr(shape, "image")]
        units.append({
            "unit_identifier": f"幻灯片 {i + 1}",
            "text": slide_text,
            "images": images
        })
    logging.info(f"从PPTX中提取了 {len(units)} 个幻灯片单元。")
    return units

def _extract_from_pdf(file_stream: IO[bytes]) -> List[DocumentUnit]:
    doc = fitz.open(stream=file_stream, filetype="pdf")
    units: List[DocumentUnit] = []
    for i, page in enumerate(doc):
        page_text = page.get_text("text").strip()
        images_on_page = []
        for img in page.get_images(full=True):
            xref = img[0]
            base_image = doc.extract_image(xref)
            images_on_page.append(base_image["image"])
        units.append({
            "unit_identifier": f"页面 {i + 1}",
            "text": page_text,
            "images": images_on_page
        })
    logging.info(f"从PDF中提取了 {len(units)} 个页面单元。")
    return units

def _extract_from_docx(file_stream: IO[bytes]) -> List[DocumentUnit]:
    document = docx.Document(file_stream)
    full_text = "\n".join([para.text for para in document.paragraphs]).strip()
    images = [rel.target_part.blob for rel in document.part.rels.values() if "image" in rel.target_ref]
    unit: DocumentUnit = { "unit_identifier": "文档内容", "text": full_text, "images": images }
    logging.info(f"从DOCX中提取了 1 个文档单元，包含 {len(images)} 张图片。")
    return [unit]

def _extract_from_xlsx(file_stream: IO[bytes]) -> List[DocumentUnit]:
    workbook = openpyxl.load_workbook(file_stream)
    units: List[DocumentUnit] = []
    for sheet in workbook.worksheets:
        unit_identifier = f"工作表 '{sheet.title}'"
        sheet_text = "\n".join(str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None).strip()
        images = [image.ref for image in sheet._images] if hasattr(sheet, '_images') else []
        if sheet_text or images:
             units.append({ "unit_identifier": unit_identifier, "text": sheet_text, "images": images })
    logging.info(f"从XLSX中提取了 {len(units)} 个工作表单元。")
    return units

# VVVV  核心逻辑重构 VVVV
def process_document_images(file_content: bytes, filename: str) -> str:
    """
    主流程函数：解析文档，对每个单元进行分析。如果单元内图片过多，则先分批分析，再聚合结果。
    """
    file_ext = filename.split('.')[-1].lower()
    file_stream = io.BytesIO(file_content)

    extraction_map = {
        'pptx': _extract_from_pptx,
        'pdf': _extract_from_pdf,
        'docx': _extract_from_docx,
        'xlsx': _extract_from_xlsx,
    }
    if file_ext not in extraction_map:
        raise DocumentParsingError(f"不支持的文件类型。当前支持 'pptx', 'pdf', 'docx', 'xlsx'。")

    document_units = extraction_map[file_ext](file_stream)
    
    # VVVV  这里是第一个修改点 VVVV
    if not any(unit['images'] for unit in document_units):
        logging.info("在文档中未找到图片，将返回提取的文本内容。")
        all_texts = [f"--- {unit['unit_identifier']} ---\n{unit['text']}" for unit in document_units if unit['text']]
        # 将返回的字典改为返回一个格式化的字符串
        return f"文档中未找到图片，返回提取的文本内容。\n\n" + "\n\n".join(all_texts)

    # --- 阶段一：并行分析所有图片批次 ---
    analysis_tasks = []
    STAGE1_PROMPT_TEMPLATE = """你是一个专业的文档分析助手。任务是结合我提供的“页面文字”和一组“页面上的图片”，生成对这个页面**当前批次内容**的综合性描述。
你的分析应专注于当前提供的信息，并使用Markdown格式排版。尽可能保留原有的所有文字。如果你觉得图片与文字无关，那么请直接输出文字和你对图片的描述。

---
**{unit_identifier}的文字**:
{text}
---
**{unit_identifier}的图片** (本批次共{image_count}张):
[图片内容已提供，请开始分析]"""

    for unit in document_units:
        if unit['images']:
            # 每个单元的图片按8个一批进行分割
            for i, image_chunk in enumerate(_chunk_list(unit['images'], 8)):
                prompt = STAGE1_PROMPT_TEMPLATE.format(
                    unit_identifier=unit['unit_identifier'],
                    text=unit['text'],
                    image_count=len(image_chunk)
                )
                # 任务元组现在包含一个唯一的批次ID，用于后续聚合
                task_info = (unit['unit_identifier'], i)
                analysis_tasks.append((prompt, image_chunk, task_info))
    
    # 使用 defaultdict(list) 来收集同一单元的所有分析结果
    per_unit_analysis_results = defaultdict(list)
    MAX_WORKERS = 5
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {
            executor.submit(model_interactor.get_model_response, prompt, image_bytes_list, model="doubao-seed-1-6-flash-250715"): info
            for prompt, image_bytes_list, info in analysis_tasks
        }
        for future in as_completed(future_to_info):
            unit_identifier, chunk_index = future_to_info[future]
            try:
                result = future.result()
                per_unit_analysis_results[unit_identifier].append(result)
            except Exception as e:
                error_message = f"批次 {chunk_index} 分析失败: {e}"
                per_unit_analysis_results[unit_identifier].append(error_message)

    logging.info(f"阶段一分析完成，正在准备阶段二聚合或组装。")

    # --- 阶段二：按原始顺序处理每个单元（聚合或直接使用） ---
    final_content_parts = []
    STAGE2_AGGREGATION_PROMPT = """你是一个高级内容编辑。你收到了针对【同一个文档页面/单元】的几份独立分析报告，这是因为该页面的图片过多被分批处理了。你的任务是将这些分散的、描述同一页面的报告，合并成一份最终的、连贯的、完整的分析。

请严格遵循以下规则：
1.  **无缝合并**：消除报告间的重复引言和割裂感，将内容融合成一段流畅的文本。
2.  **保留所有细节**：确保原始报告中提到的所有图片分析和文本要点都被包含在最终版本中。尽可能保留原有的所有文字。
3.  **单一视角**：最终的输出应该读起来像是对这一个页面的一次性完整分析。
4.  **Markdown格式**: 使用合适的Markdown标题和格式来组织最终报告。

---
**来自【{unit_identifier}】的多份独立分析报告**:
{combined_analyses}
---
请根据以上报告，为【{unit_identifier}】生成最终的、合并后的一份综合性分析。"""

    for unit in document_units:
        identifier = unit['unit_identifier']
        
        # 案例 A: 单元无图片，直接使用原文
        if not unit['images']:
            if unit['text']:
                final_content_parts.append(f"--- {identifier} (无图片) ---\n{unit['text']}")
            continue

        analyses = per_unit_analysis_results.get(identifier, [])
        
        # 案例 B: 单元有图片，但只产生了一份分析报告（无需聚合）
        if len(analyses) == 1:
            logging.info(f"单元 '{identifier}' 无需聚合，直接使用分析结果。")
            final_content_parts.append(f"### 对 {identifier} 的分析\n{analyses[0]}")
        
        # 案例 C: 单元有图片，且产生了多份报告（需要聚合）
        elif len(analyses) > 1:
            logging.info(f"单元 '{identifier}' 检测到 {len(analyses)} 个分析批次，正在执行聚合...")
            combined_analyses = "\n\n---\n".join(analyses)
            final_prompt = STAGE2_AGGREGATION_PROMPT.format(
                unit_identifier=identifier,
                combined_analyses=combined_analyses
            )
            # VVVV 核心修改 VVVV
            try:
                # 调用模型进行文本到文本的聚合
                aggregated_result = model_interactor.get_model_response(
                    prompt=final_prompt,
                    model="doubao-seed-1-6-flash-250715"
                )
                final_content_parts.append(aggregated_result)
            except Exception as e:
                logging.error(f"单元 '{identifier}' 的聚合步骤失败: {e}")
                # 降级处理：返回未聚合的原始内容和一条错误消息
                error_header = f"### 对 {identifier} 的分析 (聚合失败)\n\n**错误**: 未能将以下分批报告合并成最终版本。已为您呈现原始报告：\n\n---"
                final_content_parts.append(error_header + "\n\n" + combined_analyses)
            # ^^^^ 核心修改 ^^^^
             
    # --- 最终返回 ---
    final_report = "\n\n".join(final_content_parts)
    return final_report.strip()