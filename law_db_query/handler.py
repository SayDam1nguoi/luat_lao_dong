from law_db_query.intent import is_law_article_query
from law_db_query.parser import parse_law_query
from law_db_query.db import query_article_from_db

def handle_law_article_query(message: str) -> str | None:
    """
    Nếu là câu hỏi Điều luật → trả text
    Nếu không → return None (để chatbot xử lý bình thường)
    """
    if not is_law_article_query(message):
        return None

    law_names, article = parse_law_query(message)
    result = query_article_from_db(law_names, article)

    if not result:
        return " Không tìm thấy điều luật bạn yêu cầu."

    ln, ly, ch, sec, art, text = result

    return (
        f" **{ln} ({ly})**\n"
        f"Chương: {ch} | Mục: {sec} | Điều: {art}\n\n"
        f"{text}"
    )
