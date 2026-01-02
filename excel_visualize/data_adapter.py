# data_adapter.py

import pandas as pd
import re


# ==================================================
# 1️⃣ PRICE DATA (GIỮ NGUYÊN)
# ==================================================
def extract_price_data_by_province(excel_handler, province: str):
    df = excel_handler.df

    df_filtered = df[
        df["Tỉnh/Thành phố"].str.lower().str.strip() == province.lower()
    ][["Tên", "Giá thuê đất"]].dropna()

    return df_filtered


def extract_price_data(
    excel_handler,
    province: str,
    industrial_type: str
):
    df = excel_handler.df.copy()

    df["Loại_norm"] = (
        df["Loại"]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    if industrial_type == "Cụm công nghiệp":
        type_mask = df["Loại_norm"].str.contains(r"cụm|ccn", regex=True)
    elif industrial_type == "Khu công nghiệp":
        type_mask = df["Loại_norm"].str.contains(r"khu|kcn", regex=True)
    else:
        return df.iloc[0:0]

    df_filtered = df[
        (df["Tỉnh/Thành phố"].str.lower().str.strip() == province.lower())
        & type_mask
    ][["Tên", "Giá thuê đất"]].dropna()

    return df_filtered


# ==================================================
# 2️⃣ AREA DATA – 🔥 DẤU CHẤM LÀ THẬP PHÂN
# ==================================================
def _parse_area_to_float(value) -> float | None:
    """
    Chuẩn hóa diện tích:
    - '77.48 ha'  → 77.48
    - '120.5'    → 120.5
    - '250 ha'   → 250.0

    ⚠️ Dấu chấm (.) là thập phân
    """
    if pd.isna(value):
        return None

    s = str(value).lower().strip()

    # Bỏ đơn vị
    s = re.sub(r"(ha|hecta)", "", s)

    # Bỏ khoảng trắng
    s = s.replace(" ", "")

    # 🚫 KHÔNG đụng vào dấu '.'
    # 🚫 KHÔNG convert thousand-separator

    try:
        return float(s)
    except ValueError:
        return None


def extract_area_data(
    excel_handler,
    province: str,
    industrial_type: str
):
    """
    Trích xuất dữ liệu tổng diện tích (float)
    """
    df = excel_handler.df.copy()

    df["Loại_norm"] = (
        df["Loại"]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    if industrial_type == "Cụm công nghiệp":
        type_mask = df["Loại_norm"].str.contains(r"cụm|ccn", regex=True)
    elif industrial_type == "Khu công nghiệp":
        type_mask = df["Loại_norm"].str.contains(r"khu|kcn", regex=True)
    else:
        return df.iloc[0:0]

    df_filtered = df[
        (df["Tỉnh/Thành phố"].str.lower().str.strip() == province.lower())
        & type_mask
    ][["Tên", "Tổng diện tích"]].copy()

    # 🔥 CHUẨN HÓA DIỆN TÍCH
    df_filtered["Tổng diện tích"] = df_filtered["Tổng diện tích"].apply(
        _parse_area_to_float
    )

    df_filtered = df_filtered.dropna(subset=["Tổng diện tích"])

    return df_filtered
