# File: excel_visualize/handler.py
import pandas as pd
from .rag_core import rag_agent
from .data_adapter import clean_numeric_data, _parse_price_to_float, _parse_area_to_float

# 1. BỔ SUNG IMPORT CÁC HÀM VẼ MỚI
from .chart import (
    plot_price_bar_chart_base64, 
    plot_area_bar_chart_base64, 
    plot_dual_bar_chart_base64,
    plot_horizontal_bar_chart, # Mới
    plot_pie_chart,            # Mới
    plot_line_chart            # Mới
)

def handle_excel_visualize(message: str) -> dict:
    """
    Xử lý yêu cầu visualize: 
    - Xác định dữ liệu (Giá/Diện tích/Dual).
    - Xác định loại biểu đồ (Bar/Line/Pie/Barh).
    """
    # 1. Query RAG Agent
    query_result = rag_agent.retrieve_filters(message)
    
    if query_result.get("filter_type") == "error":
        return _error_response(query_result.get("message", "Lỗi xử lý câu hỏi."))

    df_filtered = query_result.get("data")
    industrial_type = query_result.get("industrial_type", "Khu công nghiệp")
    
    # Lấy thông tin từ RAG
    viz_metric = query_result.get("visualization_metric", "dual") # price, area, dual
    chart_type = query_result.get("chart_type", "bar")            # bar, barh, pie, line

    # 2. Kiểm tra dữ liệu chung
    if df_filtered is None or df_filtered.empty:
        return _error_response(f"Không tìm thấy {industrial_type} nào phù hợp.")

    found_provinces = df_filtered["Tỉnh/Thành phố"].unique().tolist()
    province_str = ", ".join(found_provinces) if found_provinces else "Khu vực tìm kiếm"

    # =======================================================
    # TRƯỜNG HỢP 1: BIỂU ĐỒ ĐÔI (DUAL) - GIÁ & DIỆN TÍCH
    # =======================================================
    # Lưu ý: Biểu đồ đôi phức tạp, hiện tại chỉ hỗ trợ tốt nhất ở dạng Cột (Bar).
    # Nếu user đòi vẽ Pie cho Dual -> Không khả thi -> Fallback về Dual Bar.
    if viz_metric == "dual":
        df_dual = df_filtered.copy()
        df_dual["Giá số"] = df_dual["Giá thuê đất"].apply(_parse_price_to_float)
        df_dual["Diện tích số"] = df_dual["Tổng diện tích"].apply(_parse_area_to_float)
        
        # Lọc dòng có ít nhất 1 trong 2 dữ liệu
        df_dual = df_dual.dropna(subset=["Giá số", "Diện tích số"], how="all")
        
        if df_dual.empty:
            return _error_response("Không có đủ dữ liệu giá hoặc diện tích để vẽ biểu đồ tổng quan.")

        # Gọi hàm vẽ biểu đồ đôi chuyên dụng
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

    # =======================================================
    # TRƯỜNG HỢP 2: BIỂU ĐỒ ĐƠN (SINGLE) - GIÁ HOẶC DIỆN TÍCH
    # =======================================================
    else:
        is_price = (viz_metric == "price")
        
        # 1. Làm sạch dữ liệu
        df_plot = clean_numeric_data(df_filtered, is_price_metric=is_price)
        if df_plot.empty: 
            return _error_response(f"Thiếu dữ liệu về {'Giá' if is_price else 'Diện tích'} để vẽ.")
        
        # 2. Cấu hình tham số vẽ (Màu sắc, Đơn vị, Tên cột)
        col_name = "Giá số" if is_price else "Diện tích số"
        unit = "USD/m²/năm" if is_price else "ha"
        color = "#1f77b4" if is_price else "#2ca02c" # Xanh dương (Giá) / Xanh lá (Diện tích)
        metric_vn = "GIÁ THUÊ" if is_price else "DIỆN TÍCH"
        
        # Tiêu đề đầy đủ
        full_title = f"{metric_vn} {industrial_type.upper()}\nTẠI {province_str.upper()}"

        # 3. SWITCH: Chọn hàm vẽ dựa trên chart_type
        if chart_type == "pie":
            # Vẽ biểu đồ Tròn
            chart_base64 = plot_pie_chart(df_plot, full_title, col_name, unit)
            
        elif chart_type == "line":
            # Vẽ biểu đồ Đường
            chart_base64 = plot_line_chart(df_plot, full_title, col_name, color, unit)
            
        elif chart_type == "barh":
            # Vẽ biểu đồ Cột Ngang
            chart_base64 = plot_horizontal_bar_chart(df_plot, full_title, col_name, color, unit)
            
        else:
            # Mặc định: Vẽ biểu đồ Cột Đứng (Vertical Bar)
            if is_price:
                chart_base64 = plot_price_bar_chart_base64(df_plot, province_str, industrial_type)
            else:
                chart_base64 = plot_area_bar_chart_base64(df_plot, province_str, industrial_type)

        # 4. Tạo Items trả về
        items = []
        for _, row in df_filtered.iterrows():
            val = row.get("Giá thuê đất", "N/A") if is_price else row.get("Tổng diện tích", "N/A")
            items.append({
                "name": row.get("Tên", ""),
                viz_metric: val
            })

        return {
            "type": f"excel_visualize_{viz_metric}",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": viz_metric,
            "chart_type": chart_type, # Trả về để debug nếu cần
            "items": items,
            "chart_base64": chart_base64,
            "text": f"Đã vẽ {chart_type.replace('pie','biểu đồ tròn').replace('line','biểu đồ đường').replace('barh','biểu đồ ngang').replace('bar','biểu đồ cột')} về {metric_vn.lower()} tại {province_str}."
        }

def _error_response(msg):
    return {"type": "error", "message": msg}