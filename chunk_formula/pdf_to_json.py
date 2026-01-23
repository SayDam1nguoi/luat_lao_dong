import re
import json
from pypdf import PdfReader
import tiktoken
import os

# ======================================================
# CONFIG
# ======================================================
PDF_PATH = r"C:\Users\tabao\OneDrive\Desktop\cong_viec_lam\temp_data\pdf_test.pdf"
OUTPUT_JSON = "pdf_full_content.json"

enc = tiktoken.get_encoding("cl100k_base")

# ======================================================
# UTILS
# ======================================================
def token_count(text: str) -> int:
    return len(enc.encode(text))

def clean_text_basic(text: str) -> str:
    """
    Làm sạch cơ bản:
    - bỏ gạch nối xuống dòng
    - gộp từ bị vỡ
    - chuẩn hóa khoảng trắng
    - GIỮ NGUYÊN NỘI DUNG
    """
    if not text:
        return ""

    # bỏ gạch nối xuống dòng
    text = re.sub(r"-\n", "", text)

    # gộp từ bị vỡ: "thủy \n lực" -> "thủy lực"
    text = re.sub(r"(\w)\n(\w)", r"\1 \2", text)

    # chuẩn hóa khoảng trắng
    text = re.sub(r"[ \t]+", " ", text)

    # chuẩn hóa newline
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

def read_pdf_full(path: str) -> list[str]:
    reader = PdfReader(path)
    pages = []
    for p in reader.pages:
        raw = p.extract_text() or ""
        pages.append(clean_text_basic(raw))
    return pages

# ======================================================
# MAIN
# ======================================================
print("📖 Đang đọc toàn bộ PDF...")

pages = read_pdf_full(PDF_PATH)
full_text = "\n\n".join(pages)

output = {
    "source": os.path.basename(PDF_PATH),
    "num_pages": len(pages),
    "total_tokens": token_count(full_text),
    "content": full_text
}

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ DONE")
print(f"📄 File: {OUTPUT_JSON}")
print(f"📑 Pages: {output['num_pages']}")
print(f"🔢 Tokens: {output['total_tokens']:,}")
