import pandas as pd
from .rag_core import rag_agent
from .data_adapter import clean_numeric_data, _parse_price_to_float, _parse_area_to_float

# 1. BỔ SUNG IMPORT CÁC HÀM VẼ MỚI
from .chart import (
    plot_price_bar_chart_base64, 
    plot_area_bar_chart_base64, 
    plot_dual_bar_chart_base64,
    plot_horizontal_bar_chart, 
    plot_pie_chart,            
    plot_line_chart            
)

def handle_excel_visualize(message: str) -> dict:
    """
    Xử lý yêu cầu visualize: 
    - Sắp xếp dữ liệu thống nhất (Rank 1, 2, 3...).
    - Đồng bộ số thứ tự giữa Biểu đồ và JSON.
    """
    # 1. Query RAG Agent
    query_result = rag_agent.retrieve_filters(message)
    
    if query_result.get("filter_type") == "error":
        return _error_response(query_result.get("message", "Lỗi xử lý câu hỏi."))

    df_filtered = query_result.get("data")
    industrial_type = query_result.get("industrial_type", "Khu công nghiệp")
    
    # Lấy thông tin từ RAG
    viz_metric = query_result.get("visualization_metric", "dual") 
    chart_type = query_result.get("chart_type", "bar")            

    # 2. Kiểm tra dữ liệu chung
    if df_filtered is None or df_filtered.empty:
        return _error_response(f"Không tìm thấy {industrial_type} nào phù hợp.")

    found_provinces = df_filtered["Tỉnh/Thành phố"].unique().tolist()
    province_str = ", ".join(found_provinces) if found_provinces else "Khu vực tìm kiếm"

    # Fix logic: Pie chart không vẽ Dual -> Ép về Area
    if chart_type == "pie" and viz_metric in ["dual", "price"]:
        viz_metric = "area"

    # =======================================================
    # TRƯỜNG HỢP 1: BIỂU ĐỒ ĐÔI (DUAL) - GIÁ & DIỆN TÍCH
    # =======================================================
    if viz_metric == "dual":
        df_dual = df_filtered.copy()
        df_dual["Giá số"] = df_dual["Giá thuê đất"].apply(_parse_price_to_float)
        df_dual["Diện tích số"] = df_dual["Tổng diện tích"].apply(_parse_area_to_float)
        
        # Lọc dòng có ít nhất 1 trong 2 dữ liệu
        df_dual = df_dual.dropna(subset=["Giá số", "Diện tích số"], how="all")
        
        if df_dual.empty:
            return _error_response("Không có đủ dữ liệu giá hoặc diện tích để vẽ biểu đồ tổng quan.")

        # --- [QUAN TRỌNG] SẮP XẾP DỮ LIỆU ---
        # Sắp xếp theo Giá giảm dần, nếu giá bằng nhau thì xét Diện tích
        df_sorted = df_dual.sort_values(by=["Giá số", "Diện tích số"], ascending=[False, False])

        # Gọi hàm vẽ (truyền df đã sort)
        chart_base64 = plot_dual_bar_chart_base64(df_sorted, province_str, industrial_type)
        
        # Tạo items (Theo đúng thứ tự đã sort)
        items = []
        for idx, row in enumerate(df_sorted.iterrows()):
            _, r = row
            items.append({
                "index": idx + 1, # Thêm số thứ tự 1, 2, 3...
                "name": r.get("Tên", ""),
                "price": r.get("Giá thuê đất", "N/A"),
                "area": r.get("Tổng diện tích", "N/A")
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
        
        # 2. Cấu hình tham số
        col_name = "Giá số" if is_price else "Diện tích số"
        unit = "USD/m²/năm" if is_price else "ha"
        color = "#1f77b4" if is_price else "#2ca02c"
        metric_vn = "GIÁ THUÊ" if is_price else "DIỆN TÍCH"
        full_title = f"{metric_vn} {industrial_type.upper()}\nTẠI {province_str.upper()}"

        # --- [QUAN TRỌNG] SẮP XẾP DỮ LIỆU ---
        # Sắp xếp giảm dần (Lớn nhất đứng đầu)
        df_sorted = df_plot.sort_values(by=col_name, ascending=False)

        # 3. SWITCH: Chọn hàm vẽ (Truyền df_sorted)
        if chart_type == "pie":
            chart_base64 = plot_pie_chart(df_sorted, full_title, col_name, unit)
        elif chart_type == "line":
            chart_base64 = plot_line_chart(df_sorted, full_title, col_name, color, unit)
        elif chart_type == "barh":
            chart_base64 = plot_horizontal_bar_chart(df_sorted, full_title, col_name, color, unit)
        else:
            if is_price:
                chart_base64 = plot_price_bar_chart_base64(df_sorted, province_str, industrial_type)
            else:
                chart_base64 = plot_area_bar_chart_base64(df_sorted, province_str, industrial_type)

        # 4. Tạo Items (Theo đúng thứ tự đã sort)
        items = []
        for idx, row in enumerate(df_sorted.iterrows()):
            _, r = row
            val = r.get("Giá thuê đất", "N/A") if is_price else r.get("Tổng diện tích", "N/A")
            items.append({
                "index": idx + 1, # Thêm số thứ tự 1, 2, 3...
                "name": r.get("Tên", ""),
                viz_metric: val
            })

        return {
            "type": f"excel_visualize_{viz_metric}",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": viz_metric,
            "chart_type": chart_type,
            "items": items,
            "chart_base64": chart_base64,
            "text": f"Đã vẽ {chart_type.replace('pie','biểu đồ tròn').replace('line','biểu đồ đường').replace('barh','biểu đồ ngang').replace('bar','biểu đồ cột')} về {metric_vn.lower()} tại {province_str}."
        }

def _error_response(msg):
    return {"type": "error", "message": msg}