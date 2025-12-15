import pdfplumber
import json

# ====== ĐƯỜNG DẪN FILE PDF ======
pdf_path = r"C:\Users\tabao\Downloads\Quyết định-36-2025-QĐ-TTg.pdf"

# ====== FILE OUTPUT JSON ======
output_json = r"ma_nganh.json"

# Kết quả cuối cùng
result = {}

def extract_code(row):
    """
    Lấy mã ngành từ 1 hàng bảng.
    Hỗ trợ đầy đủ Cấp 1 → Cấp 5:
    - Cấp 1: A, B, C...
    - Cấp 2: 01, 02...
    - Cấp 3: 011, 012...
    - Cấp 4: 0111, 0123...
    - Cấp 5: 01110, 01230...
    """

    candidates = []

    for cell in row:
        if not cell:
            continue

        cell_clean = cell.strip()

        # Cấp 1 (A, B, C...)
        if len(cell_clean) == 1 and cell_clean.isalpha():
            candidates.append(cell_clean)
            continue

        # Cấp 2–5 chỉ gồm số
        if cell_clean.isdigit() and 2 <= len(cell_clean) <= 5:
            candidates.append(cell_clean)

    if not candidates:
        return None

    # Luôn chọn mã dài nhất (ưu tiên cấp sâu hơn)
    return max(candidates, key=len)


with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()

        if not tables:
            continue

        for table in tables:
            for row in table:
                # Bỏ các hàng trống hoàn toàn
                if not any(cell and cell.strip() for cell in row):
                    continue

                code = extract_code(row)
                name = row[-1].strip() if row[-1] else None

                if code and name:
                    result[code] = name


# Lưu ra file JSON
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

print("✔ ĐÃ TRÍCH XUẤT THÀNH CÔNG!")
print(f"✔ File JSON lưu tại: {output_json}")
print(f"✔ Tổng số mã ngành thu được: {len(result)}")
