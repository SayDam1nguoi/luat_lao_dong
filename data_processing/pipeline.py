# data_processing/pipeline.py
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

from data_processing.cleaning import clean_question_remove_uris
from data_processing.language import detect_language_openai, convert_language
from data_processing.context_builder import build_context_from_hits
from system_prompts.pdf_reader_system import PDF_READER_SYS


def process_pdf_question(
    i: Dict[str, Any],
    *,
    llm,
    lang_llm,
    retriever,
    retriever_vsic_2018=None,
    excel_handler=None
) -> str:
    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])

    clean_question = clean_question_remove_uris(message)
    user_lang = detect_language_openai(message, lang_llm)

    # 1️⃣ Excel ưu tiên
    if excel_handler:
        handled, excel_response = excel_handler.process_query(clean_question)
        if handled and excel_response:
            return (
                convert_language(excel_response, user_lang, lang_llm)
                if user_lang != "vi"
                else excel_response
            )

    # 2️⃣ VectorDB – VSIC hiện hành (2025)
    if retriever is None:
        msg = "VectorDB chưa sẵn sàng."
        return convert_language(msg, user_lang, lang_llm)

    hits_2025 = retriever.invoke(clean_question)
    context_2025 = build_context_from_hits(hits_2025) if hits_2025 else ""

    # 3️⃣ Hits VSIC 2018 – đối chứng
    hits_2018 = []
    context_2018 = ""
    if retriever_vsic_2018:
        hits_2018 = retriever_vsic_2018.invoke(clean_question)
        context_2018 = build_context_from_hits(hits_2018) if hits_2018 else (
            "⚠️ Mã ngành này không được quy định trong Hệ thống ngành kinh tế Việt Nam "
            "ban hành theo Quyết định số 27/2018/QĐ-TTg (VSIC 2018)."
        )

    # Nếu cả 2025 và 2018 đều không tìm thấy
    if not hits_2025 and not hits_2018:
        msg = "Không tìm thấy thông tin ngành nghề phù hợp."
        return convert_language(msg, user_lang, lang_llm)

    # Prefix hướng dẫn cho LLM
    system_prompt = (
        PDF_READER_SYS
        + f"\n\n🌍 Người dùng đang dùng ngôn ngữ: '{user_lang}'."
        + "\n\n🌟 Đối chiếu VSIC 2018 và 2025 (nếu có): "
          "Phải nêu rõ mã ngành, tên ngành, phân ngành, nhóm ngành, và nếu thay đổi, tách/gộp, "
          "hoặc không tồn tại, ghi chú rõ ràng."
    )

    messages = [SystemMessage(content=system_prompt)]
    if history:
        messages.extend(history[-10:])

    # Gửi context VSIC 2025 và VSIC 2018 cho LLM
    messages.append(
        HumanMessage(
            content=f"""
Câu hỏi: {clean_question}

Nội dung VSIC 2025 (hiện hành):
{context_2025}

Nội dung VSIC 2018 (đối chứng):
{context_2018}

Hãy trả lời đầy đủ, bao gồm so sánh giữa VSIC 2025 và VSIC 2018.
Hãy tuân thủ tuyệt đối các quy định: không tóm tắt, không bỏ sót, nêu rõ căn cứ pháp lý.
Hãy trả lời bằng ngôn ngữ: {user_lang}.
"""
        )
    )

    response = llm.invoke(messages).content

    detected = detect_language_openai(response, lang_llm)
    if detected != user_lang:
        response = convert_language(response, user_lang, lang_llm)

    return response
