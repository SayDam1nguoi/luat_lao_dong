from .data_adapter import (
    extract_price_data,
    extract_area_data
)
from .chart import (
    plot_price_bar_chart_base64,
    plot_area_bar_chart_base64
)
from .intent import (
    detect_industrial_type,
    detect_excel_metric
)


def extract_province_from_excel(message: str, excel_handler) -> str | None:
    msg = message.lower()

    provinces = (
        excel_handler.df["Tỉnh/Thành phố"]
        .dropna()
        .astype(str)
        .unique()
    )

    # Ưu tiên tỉnh có tên dài hơn (VD: Bà Rịa - Vũng Tàu)
    for province in sorted(provinces, key=len, reverse=True):
        if province.lower() in msg:
            return province

    return None


def handle_excel_visualize(message: str, excel_handler):
    # =========================
    # 0️⃣ Validate handler
    # =========================
    if excel_handler is None:
        return {
            "type": "error",
            "message": "Chưa cấu hình dữ liệu Excel."
        }

    # =========================
    # 1️⃣ Province
    # =========================
    province = extract_province_from_excel(message, excel_handler)
    if not province:
        return {
            "type": "error",
            "message": "Vui lòng nêu rõ tỉnh/thành phố."
        }

    # =========================
    # 2️⃣ Industrial type
    # =========================
    industrial_type = detect_industrial_type(message)
    if not industrial_type:
        return {
            "type": "error",
            "message": (
                "Vui lòng cho biết bạn muốn xem "
                "**khu công nghiệp** hay **cụm công nghiệp**."
            )
        }

    # =========================
    # 3️⃣ Metric (price / area)
    # =========================
    metric = detect_excel_metric(message)
    if not metric:
        return {
            "type": "error",
            "message": (
                "Vui lòng cho biết bạn muốn so sánh "
                "**giá thuê đất** hay **tổng diện tích**."
            )
        }

    # =========================
    # 4️⃣ PRICE CHART
    # =========================
    if metric == "price":
        df = extract_price_data(
            excel_handler=excel_handler,
            province=province,
            industrial_type=industrial_type
        )

        if df.empty:
            return {
                "type": "error",
                "message": (
                    f"Không có dữ liệu {industrial_type.lower()} "
                    f"tại {province}."
                )
            }

        chart_base64 = plot_price_bar_chart_base64(
            df,
            province,
            industrial_type
        )

        return {
            "type": "excel_visualize_price",
            "province": province,
            "industrial_type": industrial_type,
            "metric": "price",
            "items": [
                {
                    "name": row["Tên"],
                    "price": row["Giá thuê đất"]
                }
                for _, row in df.iterrows()
            ],
            "chart_base64": chart_base64
        }

    # =========================
    # 5️⃣ AREA CHART
    # =========================
    if metric == "area":
        df = extract_area_data(
            excel_handler=excel_handler,
            province=province,
            industrial_type=industrial_type
        )

        if df.empty:
            return {
                "type": "error",
                "message": (
                    f"Không có dữ liệu {industrial_type.lower()} "
                    f"tại {province}."
                )
            }

        chart_base64 = plot_area_bar_chart_base64(
            df,
            province,
            industrial_type
        )

        return {
            "type": "excel_visualize_area",
            "province": province,
            "industrial_type": industrial_type,
            "metric": "area",
            "items": [
                {
                    "name": row["Tên"],
                    "area": row["Tổng diện tích"]
                }
                for _, row in df.iterrows()
            ],
            "chart_base64": chart_base64
        }

    # =========================
    # 6️⃣ Fallback (không bao giờ nên xảy ra)
    # =========================
    return {
        "type": "error",
        "message": "Không xác định được loại biểu đồ cần hiển thị."
    }
