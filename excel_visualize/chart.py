import matplotlib.pyplot as plt
import io
import base64


def _clean_name(name: str, province: str) -> str:
    """
    Bỏ các tiền tố không cần thiết:
    - khu công nghiệp / cụm công nghiệp
    - tên tỉnh
    """
    n = name.lower()
    for kw in [
        "khu công nghiệp",
        "cụm công nghiệp",
        province.lower()
    ]:
        n = n.replace(kw, "")
    return n.strip().title()


def plot_price_bar_chart_base64(
    df,
    province: str,
    industrial_type: str
) -> str:

    # =========================
    # 1️⃣ Chuẩn hóa & sort
    # =========================
    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(
        lambda x: _clean_name(x, province)
    )

    df = df.sort_values(by="Giá thuê đất", ascending=True)

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá thuê đất"].tolist()

    # =========================
    # 2️⃣ Vẽ biểu đồ (DÀI HƠN)
    # =========================
    plt.figure(figsize=(18, 6))  # 👈 kéo dài chiều ngang

    bars = plt.bar(names, prices)

    # 👇 TÊN TRỤC X THẲNG
    plt.xticks(rotation=0, ha="center")

    plt.xlabel("Khu / Cụm")
    plt.ylabel("USD / m² / năm")

    plt.title(
        f"So sánh giá thuê đất {industrial_type} – {province}"
    )

    # =========================
    # 3️⃣ Hiển thị giá trên đầu cột
    # =========================
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{int(height)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    # 👇 tránh chữ bị đè
    plt.subplots_adjust(bottom=0.25)

    # =========================
    # 4️⃣ Xuất base64
    # =========================
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    plt.close()

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


