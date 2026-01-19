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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(CURRENT_DIR, "assets", "company_logos.png")
QR_PATH = os.path.join(CURRENT_DIR, "assets", "chatiip.png")
# ============================================

def _clean_name_for_label(name: str) -> str:
    s = str(name)
    for prefix in ["Khu công nghiệp", "Cụm công nghiệp", "KCN", "CCN", "Khu CN", "Cụm CN"]:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            if s.startswith("-") or s.startswith(":"): s = s[1:].strip()
            if " - " in s: s = s.split(" - ")[0]
    return s

def _get_footer_text() -> str:
    now = datetime.now()
    time_str = now.strftime("%H:%M ngày %d/%m/%Y")
    return f"Biểu đồ được tạo bởi ChatIIP.com vào lúc {time_str}. Dữ liệu từ IIPMAP.com"

def _add_branding(fig):
    if os.path.exists(LOGO_PATH):
        try:
            img_logo = mpimg.imread(LOGO_PATH)
            logo_ax = fig.add_axes([0.85, 0.88, 0.13, 0.13], anchor='NE', zorder=10)
            logo_ax.imshow(img_logo)
            logo_ax.axis('off')
        except: pass
    if os.path.exists(QR_PATH):
        try:
            img_qr = mpimg.imread(QR_PATH)
            qr_ax = fig.add_axes([0.88, 0.02, 0.1, 0.1], anchor='SE', zorder=10)
            qr_ax.imshow(img_qr)
            qr_ax.axis('off')
        except: pass

def _plot_base64(fig) -> str:
    fig.text(0.5, 0.01, _get_footer_text(), ha='center', fontsize=10, color='#555555', style='italic')
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    base64_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return base64_str

# =========================================================
# HELPER: THÊM SỐ THỨ TỰ VÀO TÊN (1) Tên...
# =========================================================
def _get_numbered_names(df: pd.DataFrame) -> list:
    """Trả về danh sách tên có kèm số thứ tự: (1) Tên A, (2) Tên B..."""
    raw_names = df["Tên"].apply(_clean_name_for_label).tolist()
    numbered_names = []
    for i, name in enumerate(raw_names):
        numbered_names.append(f"({i+1}) {name}")
    return numbered_names

# =========================================================
# CÁC HÀM VẼ (ĐÃ UPDATE HIỂN THỊ SỐ THỨ TỰ)
# =========================================================

def plot_horizontal_bar_chart(df: pd.DataFrame, title_str: str, col_name: str, color: str, unit: str) -> str:
    # Handler đã sort DESC (Lớn nhất đầu tiên). 
    # Nhưng Barh vẽ từ dưới lên (index 0 ở dưới). Để cái Lớn nhất (số 1) nằm trên cùng, ta cần đảo ngược list khi vẽ.
    df_reversed = df.iloc[::-1] # Đảo ngược để vẽ
    
    # Tạo tên có số: Vì đảo ngược data nên số thứ tự cũng cần tính ngược lại cho khớp
    # Cách dễ nhất: Tạo list tên có số TRƯỚC khi đảo ngược
    numbered_names_desc = _get_numbered_names(df) # [(1) Max, (2) 2nd...]
    numbered_names_asc = numbered_names_desc[::-1] # [(N) Min, ..., (1) Max] - Để (1) Max nằm trên cùng
    
    values = df_reversed[col_name].tolist()
    num_items = len(values)

    fig_height = max(9, num_items * 0.5)
    fig, ax = plt.subplots(figsize=(14, fig_height))
    
    bars = ax.barh(numbered_names_asc, values, color=color, height=0.6, zorder=3)
    ax.grid(axis='x', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_xlabel(unit, fontsize=13, fontweight='bold')
    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=20, color='#333333')
    
    font_size = 10 if num_items < 30 else 8
    
    # Annotate giá trị
    for i, bar in enumerate(bars):
        width = bar.get_width()
        ax.annotate(f'{width:.1f}', 
                    xy=(width, bar.get_y() + bar.get_height()/2),
                    xytext=(5, 0), textcoords="offset points",
                    ha='left', va='center', fontweight='bold', fontsize=font_size)
        
        # Thêm Khoanh tròn số thứ tự ở cuối thanh (hoặc đầu thanh)
        # Vì data đảo ngược: i=0 là cái cuối cùng (số N), i=max là cái đầu tiên (số 1)
        # Ta lấy số từ numbered_names_asc[i]. Split ra lấy số (1)
        rank_str = numbered_names_asc[i].split(" ")[0] # Lấy "(1)"
        rank_num = rank_str.replace("(", "").replace(")", "")
        
        # Vẽ vòng tròn số ở bên trái trục Y (cạnh tên) hoặc bên phải thanh?
        # Yêu cầu: "khoanh tròn ở biểu đồ". Vẽ ở bên phải giá trị một chút.
        ax.annotate(rank_num, 
                    xy=(width, bar.get_y() + bar.get_height()/2),
                    xytext=(45, 0), textcoords="offset points", # Dịch ra xa hơn giá trị
                    ha='center', va='center', fontweight='bold', color='white',
                    bbox=dict(boxstyle="circle,pad=0.3", fc="#555555", ec="none"))

    plt.subplots_adjust(top=1 - (1.5/fig_height), bottom=0.5/fig_height, left=0.25, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_pie_chart(df: pd.DataFrame, title_str: str, col_name: str, unit: str) -> str:
    # df đã sort DESC
    names = _get_numbered_names(df)
    values = df[col_name].tolist()
    
    fig_size = 14 if len(names) < 20 else 20
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    
    wedges, texts, autotexts = ax.pie(values, labels=names, autopct='%1.1f%%', 
                                      startangle=90, counterclock=False, 
                                      textprops={'fontsize': 9}, pctdistance=0.85, labeldistance=1.05)
    
    centre_circle = plt.Circle((0,0),0.70,fc='white')
    fig.gca().add_artist(centre_circle)

    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=30, color='#333333')
    plt.setp(autotexts, size=8, weight="bold", color="black")
    
    # Pie chart thì tên đã có số (1), (2). Không cần khoanh tròn thêm vì sẽ rất rối.
    
    plt.subplots_adjust(top=0.9, bottom=0.1, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_line_chart(df: pd.DataFrame, title_str: str, col_name: str, color: str, unit: str) -> str:
    # df đã sort DESC
    names = _get_numbered_names(df)
    values = df[col_name].tolist()
    num_items = len(names)

    fig_width = max(14, num_items * 0.4)
    fig, ax = plt.subplots(figsize=(fig_width, 9))
    
    ax.plot(names, values, marker='o', linestyle='-', color=color, linewidth=2, markersize=8, zorder=3)
    ax.grid(True, linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel(unit, fontsize=13, fontweight='bold')
    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=30, color='#333333')
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=10)

    for i, txt in enumerate(values):
        # Giá trị
        ax.annotate(f"{txt:.1f}", (names[i], values[i]), xytext=(0, 10), 
                    textcoords='offset points', ha='center', fontweight='bold', fontsize=9)
        
        # Số thứ tự khoanh tròn (ngay tại điểm marker)
        ax.annotate(f"{i+1}", (names[i], values[i]), xytext=(0, -20), 
                    textcoords='offset points', ha='center', fontweight='bold', color='white', fontsize=8,
                    bbox=dict(boxstyle="circle,pad=0.2", fc="#555555", ec="none", alpha=0.8))

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_price_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    # df đã sort DESC
    names = _get_numbered_names(df)
    values = df["Giá số"].tolist()
    num_items = len(names)

    fig_width = max(14, num_items * 0.5) 
    fig, ax = plt.subplots(figsize=(fig_width, 9))
    
    bars = ax.bar(names, values, color="#1f77b4", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

    ax.set_ylabel("Giá thuê (USD/m²/năm)", fontsize=13, fontweight='bold')
    ax.set_title(f"GIÁ THUÊ ĐẤT {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=10)
    
    for i, bar in enumerate(bars):
        height = bar.get_height()
        # Giá trị
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=9)
        
        # Số thứ tự khoanh tròn (Dưới chân cột hoặc trên đầu?)
        # Chọn: Trên đầu cột, cao hơn giá trị một chút
        ax.annotate(f"{i+1}", 
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 20), textcoords="offset points", # Cao hơn số liệu
                    ha='center', va='bottom', fontweight='bold', color='white', fontsize=8,
                    bbox=dict(boxstyle="circle,pad=0.2", fc="#1f77b4", ec="white", lw=1))

    plt.subplots_adjust(top=0.85, bottom=0.35, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_area_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    names = _get_numbered_names(df)
    values = df["Diện tích số"].tolist()
    num_items = len(names)

    fig_width = max(14, num_items * 0.5)
    fig, ax = plt.subplots(figsize=(fig_width, 9))
    
    bars = ax.bar(names, values, color="#2ca02c", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel("Diện tích (ha)", fontsize=13, fontweight='bold')
    ax.set_title(f"DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=10)
    
    for i, bar in enumerate(bars):
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=9)
        
        # Số khoanh tròn
        ax.annotate(f"{i+1}", 
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 20), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', color='white', fontsize=8,
                    bbox=dict(boxstyle="circle,pad=0.2", fc="#2ca02c", ec="white", lw=1))

    plt.subplots_adjust(top=0.85, bottom=0.35, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_dual_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    # df đã sort
    names = _get_numbered_names(df)
    prices = df["Giá số"].fillna(0).tolist()
    areas = df["Diện tích số"].fillna(0).tolist()
    num_items = len(names)
    
    fig_width = max(14, num_items * 0.5)
    fig, ax1 = plt.subplots(figsize=(fig_width, 9))
    
    x = range(len(names))
    width = 0.35

    bars1 = ax1.bar([i - width/2 for i in x], prices, width, label='Giá thuê', color='#1f77b4', zorder=3)
    ax1.set_ylabel('Giá thuê (USD/m²/năm)', color='#1f77b4', fontsize=13, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    ax2 = ax1.twinx()
    bars2 = ax2.bar([i + width/2 for i in x], areas, width, label='Diện tích', color='#2ca02c', zorder=3)
    ax2.set_ylabel('Diện tích (ha)', color='#2ca02c', fontsize=13, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#2ca02c')

    ax1.set_title(f"TỔNG QUAN GIÁ & DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                  fontsize=18, fontweight='bold', pad=30, color='#333333')
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=90, ha='center', fontsize=10)

    # Annotate
    for i, bar in enumerate(bars1):
        if bar.get_height() > 0:
            ax1.annotate(f'{bar.get_height():.0f}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#1f77b4', fontweight='bold')
            
            # Số khoanh tròn (chỉ cần vẽ 1 lần cho mỗi nhóm cột, vẽ trên cột Giá)
            ax1.annotate(f"{i+1}",
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 20), textcoords="offset points",
                         ha='center', va='bottom', fontweight='bold', color='white', fontsize=8,
                         bbox=dict(boxstyle="circle,pad=0.2", fc="#555555", ec="white", lw=1))
            
    for bar in bars2:
        if bar.get_height() > 0:
            ax2.annotate(f'{int(bar.get_height())}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#2ca02c', fontweight='bold')

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc='upper left')

    plt.subplots_adjust(top=0.85, bottom=0.35, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)