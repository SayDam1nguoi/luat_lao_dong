# File: excel_visualize/chart.py
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import io
import base64
import pandas as pd
import os
from datetime import datetime

# ================= CẤU HÌNH =================
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans', 'sans-serif']

# PATH CONFIG
LOGO_PATH = r"./assets/company_logos.png"
QR_PATH = r"./assets/chatiip.png"
# ============================================

def _clean_name_for_label(name: str) -> str:
    """Làm ngắn tên KCN để hiển thị trục X cho đẹp"""
    s = str(name)
    for prefix in ["Khu công nghiệp", "Cụm công nghiệp", "KCN", "CCN", "Khu CN", "Cụm CN"]:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            if s.startswith("-") or s.startswith(":"):
                 s = s[1:].strip()
            if " - " in s:
                s = s.split(" - ")[0]
    return s

def _get_footer_text() -> str:
    """Tạo dòng chữ chân trang với thời gian thực"""
    now = datetime.now()
    time_str = now.strftime("%H:%M ngày %d/%m/%Y")
    return f"Biểu đồ được tạo bởi ChatIIP.com vào lúc {time_str}. Dữ liệu từ IIPMAP.com"

def _add_branding(fig):
    """Thêm Logo và QR vào Figure"""
    # 1. Thêm Logo (Góc trên bên phải)
    if os.path.exists(LOGO_PATH):
        try:
            img_logo = mpimg.imread(LOGO_PATH)
            # [left, bottom, width, height]
            logo_ax = fig.add_axes([0.85, 0.88, 0.13, 0.13], anchor='NE', zorder=10)
            logo_ax.imshow(img_logo)
            logo_ax.axis('off')
        except Exception as e:
            print(f"⚠️ Warning: Không thể load Logo: {e}")
    
    # 2. Thêm QR (Góc dưới bên phải)
    if os.path.exists(QR_PATH):
        try:
            img_qr = mpimg.imread(QR_PATH)
            # Vị trí góc dưới phải
            qr_ax = fig.add_axes([0.88, 0.02, 0.1, 0.1], anchor='SE', zorder=10)
            qr_ax.imshow(img_qr)
            qr_ax.axis('off')
        except Exception as e:
            print(f"⚠️ Warning: Không thể load QR: {e}")

def _plot_base64(fig) -> str:
    """Helper chuyển Matplotlib Figure sang Base64 string"""
    # Footer text
    fig.text(0.5, 0.01, _get_footer_text(), ha='center', fontsize=10, color='#555555', style='italic')

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    base64_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return base64_str

# 1. BIỂU ĐỒ GIÁ
def plot_price_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    df_sorted = df.sort_values(by="Giá số", ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Giá số"].tolist()
    
    fig, ax = plt.subplots(figsize=(14, 9))
    bars = ax.bar(names, values, color="#1f77b4", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

    ax.set_ylabel("Giá thuê (USD/m²/năm)", fontsize=13, fontweight='bold')
    ax.set_title(f"GIÁ THUÊ ĐẤT {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10)

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

# 2. BIỂU ĐỒ DIỆN TÍCH
def plot_area_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    df_sorted = df.sort_values(by="Diện tích số", ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Diện tích số"].tolist()
    
    fig, ax = plt.subplots(figsize=(14, 9))
    bars = ax.bar(names, values, color="#2ca02c", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel("Diện tích (ha)", fontsize=13, fontweight='bold')
    ax.set_title(f"DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10)

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

# 3. BIỂU ĐỒ ĐÔI (DUAL AXIS) - MỚI
def plot_dual_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    """Vẽ biểu đồ kết hợp Giá (Trục trái) và Diện tích (Trục phải)"""
    # Lấy top 10 để đỡ rối
    df_sorted = df.sort_values(by="Giá số", ascending=False).head(10)
    
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    prices = df_sorted["Giá số"].fillna(0).tolist()
    areas = df_sorted["Diện tích số"].fillna(0).tolist()
    
    x = range(len(names))
    width = 0.35

    fig, ax1 = plt.subplots(figsize=(14, 9))

    # Trục 1: Giá (Xanh dương)
    bars1 = ax1.bar([i - width/2 for i in x], prices, width, label='Giá thuê', color='#1f77b4', zorder=3)
    ax1.set_ylabel('Giá thuê (USD/m²/năm)', color='#1f77b4', fontsize=13, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    # Trục 2: Diện tích (Xanh lá)
    ax2 = ax1.twinx()
    bars2 = ax2.bar([i + width/2 for i in x], areas, width, label='Diện tích', color='#2ca02c', zorder=3)
    ax2.set_ylabel('Diện tích (ha)', color='#2ca02c', fontsize=13, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#2ca02c')

    ax1.set_title(f"TỔNG QUAN GIÁ & DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                  fontsize=18, fontweight='bold', pad=30, color='#333333')
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=90, ha='center', fontsize=11)

    # Annotate Giá
    for bar in bars1:
        if bar.get_height() > 0:
            ax1.annotate(f'{bar.get_height():.0f}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#1f77b4', fontweight='bold')
    
    # Annotate Diện tích
    for bar in bars2:
        if bar.get_height() > 0:
            ax2.annotate(f'{int(bar.get_height())}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#2ca02c', fontweight='bold')

    # Legend
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc='upper left')

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)