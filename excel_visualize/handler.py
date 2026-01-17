# File: excel_visualize/handler.py
import pandas as pd
from .rag_core import rag_agent
from .data_adapter import clean_numeric_data, _parse_price_to_float, _parse_area_to_float
from .chart import (
    plot_price_bar_chart_base64, 
    plot_area_bar_chart_base64, 
    plot_dual_bar_chart_base64 
)

def handle_excel_visualize(message: str) -> dict:
    """
    Xử lý yêu cầu visualize: Giá, Diện tích, hoặc Cả hai (Dual).
    """
    # 1. Query RAG Agent
    query_result = rag_agent.retrieve_filters(message)
    
    if query_result.get("filter_type") == "error":
        return _error_response(query_result.get("message", "Lỗi xử lý câu hỏi."))

    df_filtered = query_result.get("data")
    industrial_type = query_result.get("industrial_type", "Khu công nghiệp")
    
    # Lấy loại biểu đồ: "price", "area", "dual"
    viz_metric = query_result.get("visualization_metric", "dual")

    # 2. Kiểm tra dữ liệu
    if df_filtered is None or df_filtered.empty:
        return _error_response(f"Không tìm thấy {industrial_type} nào phù hợp.")

    found_provinces = df_filtered["Tỉnh/Thành phố"].unique().tolist()
    province_str = ", ".join(found_provinces) if found_provinces else "Khu vực tìm kiếm"

    # 3. Xử lý theo từng loại
    
    # === CHỈ GIÁ ===
    if viz_metric == "price":
        df_plot = clean_numeric_data(df_filtered, is_price_metric=True)
        if df_plot.empty: return _error_response("Thiếu dữ liệu về Giá để vẽ.")
        
        chart_base64 = plot_price_bar_chart_base64(df_plot, province_str, industrial_type)
        items = [{"name": r.get("Tên", ""), "price": r.get("Giá thuê đất", "N/A")} for _, r in df_filtered.iterrows()]
        
        return {
            "type": "excel_visualize_price",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": "price",
            "items": items,
            "chart_base64": chart_base64,
            "text": f"Đã vẽ biểu đồ giá thuê đất tại {province_str}."
        }

    # === CHỈ DIỆN TÍCH ===
    elif viz_metric == "area":
        df_plot = clean_numeric_data(df_filtered, is_price_metric=False)
        if df_plot.empty: return _error_response("Thiếu dữ liệu về Diện tích để vẽ.")
        
        chart_base64 = plot_area_bar_chart_base64(df_plot, province_str, industrial_type)
        items = [{"name": r.get("Tên", ""), "area": r.get("Tổng diện tích", "N/A")} for _, r in df_filtered.iterrows()]
        
        return {
            "type": "excel_visualize_area",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": "area",
            "items": items,
            "chart_base64": chart_base64,
            "text": f"Đã vẽ biểu đồ diện tích tại {province_str}."
        }

    # === BIỂU ĐỒ ĐÔI (DUAL) ===
    else:
        # Chuẩn bị dữ liệu cho cả 2 cột
        df_dual = df_filtered.copy()
        df_dual["Giá số"] = df_dual["Giá thuê đất"].apply(_parse_price_to_float)
        df_dual["Diện tích số"] = df_dual["Tổng diện tích"].apply(_parse_area_to_float)
        
        # Lọc những dòng có ít nhất 1 trong 2 dữ liệu
        df_dual = df_dual.dropna(subset=["Giá số", "Diện tích số"], how="all")
        
        if df_dual.empty:
            return _error_response("Không có đủ dữ liệu giá hoặc diện tích để vẽ biểu đồ tổng quan.")

        # Gọi hàm vẽ biểu đồ đôi
        chart_base64 = plot_dual_bar_chart_base64(df_dual, province_str, industrial_type)
        
        items = []
        for _, row in df_filtered.iterrows():
            items.append({
                "name": row.get("Tên", ""),
                "price": row.get("Giá thuê đất", "N/A"),
                "area": row.get("Tổng diện tích", "N/A")
            })

        return {
            "type": "excel_visualize_dual",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": "dual",
            "items": items,
            "chart_base64": chart_base64,
            "text": f"Đã vẽ biểu đồ tổng quan (Giá & Diện tích) tại {province_str}."
        }

def _error_response(msg):
    return {"type": "error", "message": msg}