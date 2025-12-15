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
    excel_handler
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

    # 2️⃣ VectorDB
    if retriever is None:
        msg = "VectorDB chưa sẵn sàng."
        return convert_language(msg, user_lang, lang_llm)

    hits = retriever.invoke(clean_question)
    if not hits:
        msg = "Không tìm thấy thông tin liên quan."
        return convert_language(msg, user_lang, lang_llm)

    context = build_context_from_hits(hits)

    system_prompt = (
        PDF_READER_SYS
        + f"\n\n🌍 Người dùng đang dùng ngôn ngữ: '{user_lang}'."
    )

    messages = [SystemMessage(content=system_prompt)]
    if history:
        messages.extend(history[-10:])

    messages.append(
        HumanMessage(
            content=f"""
Câu hỏi: {clean_question}

Nội dung liên quan:
{context}

Hãy trả lời bằng ngôn ngữ: {user_lang}.
"""
        )
    )

    response = llm.invoke(messages).content

    detected = detect_language_openai(response, lang_llm)
    if detected != user_lang:
        response = convert_language(response, user_lang, lang_llm)

    return response
