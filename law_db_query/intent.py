import re

def is_law_article_query(message: str) -> bool:
    """
    Trả True nếu câu hỏi dạng:
    - Điều 30 luật lao động
    - điều 31 luật dân sự
    """
    pattern = r"điều\s+\d+.*luật\s+.+"
    return re.search(pattern, message.lower()) is not None
