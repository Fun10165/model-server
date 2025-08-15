# src/app/utils/response_parser.py
import logging

def parse_transcription_output(transcription_result: dict) -> str:
    """
    健壮地将火山引擎的转写结果解析为带详细信息的纯文本。
    新增信息包括：说话人性别、情绪、音量和语速。
    """
    if not isinstance(transcription_result, dict):
        # 如果输入不是预期的字典格式，直接返回其字符串表示形式
        logging.warning(f"输入格式非字典，将直接返回内容: {transcription_result}")
        return str(transcription_result)

    try:
        # 安全地获取核心的 utterances 列表
        utterances = transcription_result.get('result', {}).get('utterances', [])
        
        if not utterances:
            # 如果没有分句，尝试返回全局文本
            global_text = transcription_result.get('result', {}).get('text', '未能检测到有效语音内容。')
            logging.info("未找到分句(utterances)，返回全局文本。")
            return global_text

        formatted_lines = []
        for i, utterance in enumerate(utterances):
            # --- 这是修改的核心部分 ---
            
            # 1. 提取基础信息
            text = utterance.get('text', '').strip()
            additions = utterance.get('additions', {})
            
            # 2. 设置各项信息的默认值
            speaker = '未知说话人'
            gender = '未知性别'
            emotion = '未知情绪'
            volume_db = 0.0
            speech_rate_wps = 0.0
            
            # 3. 安全地解析 'additions' 字典中的详细信息
            if isinstance(additions, dict):
                speaker = additions.get('speaker', speaker)
                gender = additions.get('gender', gender)
                emotion = additions.get('emotion', emotion)
                
                # 解析音量，并转换为浮点数进行格式化
                try:
                    volume_str = additions.get('volume', '0')
                    volume_db = float(volume_str)
                except (ValueError, TypeError):
                    logging.warning(f"解析警告: 第 {i+1} 个分句的 'volume' 值无效: {additions.get('volume')}")

                # 解析语速，并转换为浮点数进行格式化
                try:
                    speech_rate_str = additions.get('speech_rate', '0')
                    speech_rate_wps = float(speech_rate_str)
                except (ValueError, TypeError):
                    logging.warning(f"解析警告: 第 {i+1} 个分句的 'speech_rate' 值无效: {additions.get('speech_rate')}")
            else:
                 logging.warning(f"解析警告: 第 {i+1} 个分句的 'additions' 键不存在或格式不正确。")

            # --- 修改结束 ---

            # 4. 格式化输出字符串，将所有信息整合
            if text:
                details = (
                    f"性别: {gender}, "
                    f"情绪: {emotion}, "
                    f"音量: {volume_db:.2f}dB, "
                    f"语速: {speech_rate_wps:.2f} words/s"
                )
                formatted_lines.append(f"Speaker {speaker} [{details}]: {text}")
        
        if not formatted_lines:
            return "解析完成，但未提取到任何有效句子。"
            
        return "\n".join(formatted_lines)

    except Exception as e:
        # 使用更通用的 Exception 来捕获所有可能的解析错误
        logging.error(f"解析音频转写结果时发生严重错误: {e}", exc_info=True)
        return "解析转写结果时发生内部错误。"