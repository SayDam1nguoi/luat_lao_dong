# data_processing/intent.py
import re

def is_vsic_code_query(text: str) -> bool:
    """
    Nhận diện câu hỏi liên quan đến mã ngành kinh tế (VSIC)
    """

    if not text:
        return False

    t = text.lower().strip()

    if re.search(r"\b\d{5}\b", t):
        return True

    # 2️⃣ Từ khóa đặc trưng
    keywords = [
        "mã ngành",
        "ngành nghề",
        "vsic",
        "hệ thống ngành kinh tế",
        "mã kinh tế",
    ]

    return any(k in t for k in keywords)
