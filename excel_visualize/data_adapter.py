# data_adapter.py

import pandas as pd
import re
from typing import Optional


# ==================================================
# 0️⃣ PARSE HELPERS
# ==================================================
def _parse_price_to_float(value) -> Optional[float]:
    """
    Chuẩn hóa giá thuê đất:
    - '120 USD/m²/năm' -> 120
    - '85-95 USD/m²/năm' -> 90
    """
    if pd.isna(value):
        return None

    s = str(value).lower().strip()

    # bỏ đơn vị
    for kw in ["usd/m²/năm", "usd/m2/năm", "usd"]:
        s = s.replace(kw, "")
    s = s.strip()

    # trường hợp khoảng giá
    if "-" in s:
        try:
            a, b = s.split("-")
            return (float(a.strip()) + float(b.strip())) / 2
        except Exception:
            return None

    try:
        return float(s)
    except Exception:
        return None


def _parse_area_to_float(value) -> Optional[float]:
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

    try:
        return float(s)
    except ValueError:
        return None


# ==================================================
# 1️⃣ PRICE DATA
# ==================================================
def extract_price_data_by_province(excel_handler, province: str):
    df = excel_handler.df.copy()

    df_filtered = df[
        df["Tỉnh/Thành phố"].astype(str).str.lower().str.strip() == province.lower()
    ][["Tên", "Giá thuê đất"]].copy()

    # ✅ chuẩn hóa giá thành số để lọc/sort
    df_filtered["Giá số"] = df_filtered["Giá thuê đất"].apply(_parse_price_to_float)
    df_filtered = df_filtered.dropna(subset=["Giá số"])

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
        (df["Tỉnh/Thành phố"].astype(str).str.lower().str.strip() == province.lower())
        & type_mask
    ][["Tên", "Giá thuê đất"]].copy()

    # ✅ chuẩn hóa giá thành số để lọc/sort
    df_filtered["Giá số"] = df_filtered["Giá thuê đất"].apply(_parse_price_to_float)
    df_filtered = df_filtered.dropna(subset=["Giá số"])

    return df_filtered


# ==================================================
# 2️⃣ AREA DATA
# ==================================================
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
        (df["Tỉnh/Thành phố"].astype(str).str.lower().str.strip() == province.lower())
        & type_mask
    ][["Tên", "Tổng diện tích"]].copy()

    # ✅ chuẩn hóa diện tích thành float
    df_filtered["Tổng diện tích"] = df_filtered["Tổng diện tích"].apply(_parse_area_to_float)
    df_filtered = df_filtered.dropna(subset=["Tổng diện tích"])

    return df_filtered
