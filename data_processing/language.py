# data_processing/language.py
from langchain_core.messages import SystemMessage, HumanMessage

def detect_language_openai(text: str, lang_llm) -> str:
    try:
        res = lang_llm.invoke([
            SystemMessage(
                content=(
                    "Bạn là module phát hiện ngôn ngữ. "
                    "Chỉ trả về mã ISO-639-1: vi, en, ja, ko, zh, fr, es. "
                    "KHÔNG giải thích."
                )
            ),
            HumanMessage(content=text)
        ]).content
        return res.strip().lower()
    except Exception:
        return "vi"


def convert_language(text: str, target_lang: str, lang_llm) -> str:
    lang_mapping = {
        "vi": "Tiếng Việt",
        "en": "English",
        "ko": "Korean",
        "ja": "Japanese",
        "zh": "Chinese",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "th": "Thai"
    }

    target_lang_name = lang_mapping.get(target_lang, target_lang)

    try:
        return lang_llm.invoke([
            SystemMessage(
                content="Bạn là một phiên dịch chuyên nghiệp. Chỉ trả về bản dịch."
            ),
            HumanMessage(
                content=f"Dịch nội dung sau sang {target_lang_name}:\n\n{text}"
            )
        ]).content.strip()
    except Exception:
        return text
