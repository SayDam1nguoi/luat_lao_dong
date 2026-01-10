import matplotlib.pyplot as plt
import io
import base64
import os
from PIL import Image
from datetime import datetime
import pytz


# =========================
# 1️⃣ Làm sạch tên khu / cụm
# =========================
def _clean_name(name: str, province: str) -> str:
    n = str(name).lower()
    for kw in ["khu công nghiệp", "cụm công nghiệp", str(province).lower()]:
        n = n.replace(kw, "")
    return n.strip().title()


# =========================
# ✅ Vẽ số + tên (CHUẨN – KHÔNG LỆCH)
# =========================
def _draw_index_and_name(ax, names, number_y=-0.05, name_y=-0.17, fontsize_num=10, fontsize_name=9):
    """
    - number_y: vị trí số (gần trục X)
    - name_y: vị trí tên (nằm ngay dưới số)
    """
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([])  # ❌ bỏ ticklabel mặc định

    for i, name in enumerate(names):
        # 🔢 Số thứ tự (bọc tròn)
        ax.text(
            i,
            number_y,
            str(i + 1),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=fontsize_num,
            bbox=dict(
                boxstyle="circle,pad=0.25",
                facecolor="white",
                edgecolor="black",
                linewidth=1.2
            ),
            clip_on=False
        )

        # 🏷️ Tên KCN / CCN (xoay 90°, nằm NGAY DƯỚI số)
        ax.text(
            i,
            name_y,
            name,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            rotation=90,
            fontsize=fontsize_name,
            clip_on=False
        )


# =========================
# 2️⃣ Footer
# =========================
def _add_footer(fig):
    tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz_vn)
    fig.text(
        0.5,
        0.03,
        f"Biểu đồ được tạo bởi ChatIIP.com lúc {now:%H giờ %M phút ngày %d/%m/%Y}, dữ liệu từ IIPMap.com",
        ha="center",
        fontsize=14
    )


# =========================
# 3️⃣ BIỂU ĐỒ GIÁ – 1 TỈNH
# =========================
def plot_price_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()
    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))
    df = df.dropna(subset=["Giá số"]).sort_values("Giá số")

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá số"].tolist()

    fig, ax = plt.subplots(figsize=(36, 10))
    bars = ax.bar(range(len(names)), prices, width=0.6)

    # ✅ VẼ SỐ + TÊN ĐÚNG TRỤC
    _draw_index_and_name(ax, names)

    ax.set_ylabel("USD / m² / chu kì thuê", fontsize=14)
    ax.set_title(
        f"BIỂU ĐỒ SO SÁNH GIÁ THUÊ ĐẤT {industrial_type.upper()} TỈNH {province.upper()}",
        fontsize=20,
        fontweight="bold",
        pad=18
    )

    for b in bars:
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height(),
            f"{int(b.get_height())}",
            ha="center",
            va="bottom",
            fontsize=10
        )

    ax.set_ylim(0, max(prices) * 1.15)
    fig.subplots_adjust(bottom=0.45)

    _add_footer(fig)

    buf = io.BytesIO()
    fig.savefig(buf, dpi=200)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
