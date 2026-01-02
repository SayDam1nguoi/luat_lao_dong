# intent.py

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
