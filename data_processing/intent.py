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

# Vẽ flowchart
def is_flowchart_intent(message: str) -> bool:
    """
    Nhận diện intent vẽ flowchart/sơ đồ luồng/quy trình
    """
    keywords = [
        # VI
        "flowchart", "sơ đồ", "sơ đồ luồng", "luồng", "quy trình", "diagram",
        "vẽ luồng", "vẽ sơ đồ", "vẽ flow", "mermaid","vẽ"
        # EN
        "workflow", "process flow", "flow chart"
    ]
    msg = (message or "").lower()
    return any(k in msg for k in keywords)

# Chào hỏi
def is_greeting_question(question: str) -> bool:
    greetings = [
        # VI
        "xin chào", "chào", "chào bạn", "chào anh", "chào chị",
        "bạn là ai", "bạn làm được gì", "giúp tôi", "giúp mình","bạn biết làm những gì", "chatiip là gì"
        # EN
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "who are you", "what can you do", "help me"
    ]
    q = question.lower().strip()
    return any(q in g or q.startswith(g) for g in greetings)