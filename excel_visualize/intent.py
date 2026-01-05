# intent.py
import re
from typing import Optional, Dict, Any

# =========================
# 1️⃣ Visualize intent (MAIN)
# =========================
def is_excel_visualize_intent(message: str) -> bool:
    """
    Nhận diện intent trực quan hóa dữ liệu Excel
    """
    keywords = [
        "biểu đồ",
        "vẽ",
        "so sánh",
        "visualize",
        "trực quan",
        "trực quan hóa",
        "chart",
        "graph"
    ]

    msg = message.lower()
    return any(k in msg for k in keywords)


# =========================
# 1️⃣.1 BACKWARD COMPAT
# =========================
def is_excel_visualize_price_intent(message: str) -> bool:
    """
    Alias để tương thích code cũ (KHÔNG được xóa)
    """
    return is_excel_visualize_intent(message)


# =========================
# 2️⃣ Metric intent
# =========================
def detect_excel_metric(message: str) -> str | None:
    """
    Xác định người dùng muốn so sánh chỉ số nào
    """
    msg = message.lower()

    # 👉 Giá thuê đất
    price_keywords = [
        "giá",
        "giá thuê",
        "giá thuê đất",
        "giá đất"
    ]

    # 👉 Tổng diện tích
    area_keywords = [
        "diện tích",
        "tổng diện tích",
        "quy mô"
    ]

    if any(k in msg for k in price_keywords):
        return "price"

    if any(k in msg for k in area_keywords):
        return "area"

    return None


# =========================
# 3️⃣ Industrial type intent
# =========================
def detect_industrial_type(message: str) -> str | None:
    """
    Xác định loại hình: KCN / CCN
    """
    msg = message.lower()

    if (
        "khu công nghiệp" in msg
        or "kcn" in msg
    ):
        return "Khu công nghiệp"

    if (
        "cụm công nghiệp" in msg
        or "ccn" in msg
    ):
        return "Cụm công nghiệp"

    return None


# ============================================================
# 4️⃣ NEW: Parse điều kiện lọc (từ...đến..., lớn hơn, nhỏ hơn...)
# ============================================================

def _to_number(raw: str) -> Optional[float]:
    """
    Chuyển chuỗi số có thể kèm đơn vị thành float.
    Ví dụ: '120', '120.5', '120ha', '120 ha', '120usd' -> 120 / 120.5
    """
    if raw is None:
        return None

    s = raw.lower().strip()

    # bỏ dấu phẩy ngăn cách hàng nghìn: 1,200 -> 1200
    s = s.replace(",", "")

    # giữ lại số và dấu chấm
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None

    try:
        return float(m.group(1))
    except Exception:
        return None


def parse_excel_numeric_filter(message: str) -> Optional[Dict[str, Any]]:
    """
    Parse điều kiện lọc số từ câu hỏi.

    Trả về 1 dict:
    - between: {"type": "between", "min": a, "max": b}
    - gte: {"type": "gte", "value": x}
    - lte: {"type": "lte", "value": x}
    - gt:  {"type": "gt",  "value": x}
    - lt:  {"type": "lt",  "value": x}
    """
    msg = message.lower()

    # 1) "từ A đến B"
    m = re.search(r"từ\s*([0-9\.,]+(?:\s*\w+)?)\s*đến\s*([0-9\.,]+(?:\s*\w+)?)", msg)
    if m:
        a = _to_number(m.group(1))
        b = _to_number(m.group(2))
        if a is not None and b is not None:
            return {"type": "between", "min": min(a, b), "max": max(a, b)}

    # 2) "A - B" (có thể có khoảng trắng)
    m = re.search(r"([0-9\.,]+)\s*-\s*([0-9\.,]+)", msg)
    if m:
        a = _to_number(m.group(1))
        b = _to_number(m.group(2))
        if a is not None and b is not None:
            return {"type": "between", "min": min(a, b), "max": max(a, b)}

    # 3) Toán tử so sánh dạng ký hiệu: >=, <=, >, <
    m = re.search(r"(>=|<=|>|<)\s*([0-9\.,]+(?:\s*\w+)?)", msg)
    if m:
        op = m.group(1)
        val = _to_number(m.group(2))
        if val is None:
            return None
        if op == ">=":
            return {"type": "gte", "value": val}
        if op == "<=":
            return {"type": "lte", "value": val}
        if op == ">":
            return {"type": "gt", "value": val}
        if op == "<":
            return {"type": "lt", "value": val}

    # 4) Dạng tiếng Việt: lớn hơn / trên / nhiều hơn
    m = re.search(r"(lớn hơn|trên|nhiều hơn|cao hơn)\s*([0-9\.,]+(?:\s*\w+)?)", msg)
    if m:
        val = _to_number(m.group(2))
        if val is not None:
            return {"type": "gt", "value": val}

    # 5) Dạng tiếng Việt: nhỏ hơn / dưới / ít hơn / thấp hơn
    m = re.search(r"(nhỏ hơn|dưới|ít hơn|thấp hơn)\s*([0-9\.,]+(?:\s*\w+)?)", msg)
    if m:
        val = _to_number(m.group(2))
        if val is not None:
            return {"type": "lt", "value": val}

    return None


# ============================================================
# 5️⃣ NEW: API gộp để handler dùng (metric + filter)
# ============================================================
def extract_excel_visualize_constraints(message: str) -> Dict[str, Any]:
    """
    Trả về constraints để handler lọc dữ liệu và vẽ chart.
    {
      "metric": "price"/"area"/None,
      "industrial_type": "Khu công nghiệp"/"Cụm công nghiệp"/None,
      "filter": {...}/None
    }
    """
    return {
        "metric": detect_excel_metric(message),
        "industrial_type": detect_industrial_type(message),
        "filter": parse_excel_numeric_filter(message)
    }
