import re
import json
from pypdf import PdfReader
import tiktoken

# ======================================================
# CONFIG
# ======================================================
PDF_PATH = r"C:\Users\tabao\OneDrive\Desktop\cong_viec_lam\chunk_formula\BỘ GIÁO DỤC VÀ KHOA HỌC LIÊN BANG NGA-Nghia (1).pdf"
OUTPUT_JSON = "chunks_selected.json"

enc = tiktoken.get_encoding("cl100k_base")

# ======================================================
# UTILS
# ======================================================
def token_count(text: str) -> int:
    return len(enc.encode(text))

def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    texts = []
    for p in reader.pages:
        if p.extract_text():
            texts.append(p.extract_text())
    return "\n".join(texts)

def clean_pdf_text(text: str) -> str:
    """
    Fix PDF text issues:
    - Join broken words
    - Remove excessive newlines
    """
    text = re.sub(r"(\w)\n(\w)", r"\1 \2", text)
    text = re.sub(r"-\n", "", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()

# ======================================================
# REGEX – FLEXIBLE, PDF-SAFE
# ======================================================
CH1_TITLE_RE = re.compile(r"1\.\s*PHÂN\s+TÍCH\s+THỰC\s+TRẠNG", re.IGNORECASE)
SEC_11_RE    = re.compile(r"1\.1\s+Xu\s+hướng\s+phát\s+triển", re.IGNORECASE)
SEC_12_RE    = re.compile(r"1\.2\s+Chủ\s+thể\s+và\s+đối\s+tượng", re.IGNORECASE)

CH4_TITLE_RE = re.compile(r"4\.\s*CÁC\s+KẾT\s+QUẢ\s+THÍ\s+NGHIỆM", re.IGNORECASE)
SEC_41_RE    = re.compile(r"4\.1\s+Cơ\s+sở\s+tiêu\s+chuẩn\s+hiệu\s+quả", re.IGNORECASE)
SEC_42_RE    = re.compile(r"4\.2\s+Nghiên\s+cứu\s+động\s+học", re.IGNORECASE)

# Công thức đầy đủ + ID
FORMULA_FULL_RE = re.compile(
    r"([A-Za-zА-Яа-я0-9°≤≥→\.\,\+\-\*/·\(\)\s]+?)\s*\((\d+\.\d+)\)"
)

# ======================================================
# FORMULA EXTRACTION
# ======================================================
def extract_formula_objects(text: str):
    formulas = []
    for m in FORMULA_FULL_RE.finditer(text):
        formulas.append({
            "id": f"({m.group(2)})",
            "raw_text": m.group(1).strip(),
            "position": m.start()
        })
    return formulas

# ======================================================
# PIPELINE
# ======================================================
raw_text = read_pdf(PDF_PATH)
text = clean_pdf_text(raw_text)

chunks = []
cid = 0

def safe_slice(start, end):
    if start and end:
        return text[start.start():end.start()]
    if start:
        return text[start.start():]
    return ""

def add_chunk(title, content, chapter, section, semantic):
    global cid
    if not content.strip():
        return

    cid += 1
    formula_objs = extract_formula_objects(content)

    chunks.append({
        "chunk_id": cid,
        "chapter": chapter,
        "section": section,
        "title": title,
        "semantic_block": semantic,
        "formulas": [f["id"] for f in formula_objs],
        "formula_objects": formula_objs,
        "token_count": token_count(content),
        "content": content.strip()
    })

# ------------------ INTRO ------------------
m1 = CH1_TITLE_RE.search(text)
intro_text = text[:m1.start()] if m1 else text
add_chunk(
    title="MỞ ĐẦU",
    content=intro_text,
    chapter="INTRO",
    section=None,
    semantic="introduction_full"
)

# ------------------ CHAPTER 1 ------------------
m11 = SEC_11_RE.search(text)
add_chunk(
    title="Chương 1 – Phân tích thực trạng vấn đề",
    content=safe_slice(m1, m11),
    chapter="1",
    section="1",
    semantic="chapter_intro"
)

# ------------------ 1.1 ------------------
m12 = SEC_12_RE.search(text)
add_chunk(
    title="1.1 Xu hướng phát triển máy san hiện nay",
    content=safe_slice(m11, m12),
    chapter="1",
    section="1.1",
    semantic="background_review"
)

# ------------------ 1.2 ------------------
m4 = CH4_TITLE_RE.search(text)
add_chunk(
    title="1.2 Chủ thể và đối tượng nghiên cứu",
    content=safe_slice(m12, m4),
    chapter="1",
    section="1.2",
    semantic="research_scope"
)

# ------------------ CHAPTER 4 ------------------
m41 = SEC_41_RE.search(text)
add_chunk(
    title="Chương 4 – Các kết quả thí nghiệm lý thuyết",
    content=safe_slice(m4, m41),
    chapter="4",
    section="4",
    semantic="chapter_intro"
)

# ------------------ 4.1 ------------------
m42 = SEC_42_RE.search(text)
add_chunk(
    title="4.1 Cơ sở tiêu chuẩn hiệu quả của tính cơ động",
    content=safe_slice(m41, m42),
    chapter="4",
    section="4.1",
    semantic="objective_function_and_constraints"
)

# ------------------ 4.2 ------------------
add_chunk(
    title="4.2 Nghiên cứu động học của xe san",
    content=safe_slice(m42, None),
    chapter="4",
    section="4.2",
    semantic="kinematic_analysis"
)

# ======================================================
# SAVE
# ======================================================
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

print(f"✅ DONE: {len(chunks)} chunks saved to {OUTPUT_JSON}")
