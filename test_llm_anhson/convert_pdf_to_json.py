# ================= legal_parser_dieu_khoan_to_json.py =================
import pdfplumber
import re
import os
import json
import uuid
import unicodedata

# ===================== CONFIG =====================
PDF_FOLDER = r"C:\Users\tabao\OneDrive\Desktop\test_llm_anhson\pdf test folder"
OUTPUT_FOLDER = r"C:\Users\tabao\OneDrive\Desktop\test_llm_anhson\json_output"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ===================== STEP 0: PARSE LAW NAME & YEAR =====================
def normalize_law_name(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()

    stopwords = {"luat"}
    words = [w for w in text.split() if w not in stopwords]

    return " ".join(w.capitalize() for w in words)


def parse_law_meta_from_filename(filename: str):
    m_year = re.search(r"(19|20)\d{2}", filename)
    if not m_year:
        raise ValueError("Không tìm thấy năm trong tên file")

    law_year = int(m_year.group())
    name_part = filename[:m_year.start()]
    law_name = normalize_law_name(name_part)

    return law_name, law_year


# ===================== STEP 1: EXTRACT TEXT =====================
def extract_pdf_text(path):
    full = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full += t + "\n"
    return full


# ===================== STEP 2: PARSE ĐIỀU / KHOẢN =====================
def parse_law_to_json(text, law_name, law_year):
    article = None
    clause = None
    buffer = ""

    records = []

    def flush():
        nonlocal buffer, article, clause
        content = buffer.strip()
        if not content or article is None:
            buffer = ""
            return

        records.append({
            "Id": str(uuid.uuid4()),
            "LawName": law_name,
            "LawYear": law_year,
            "Article": article,
            "Clause": clause,
            "Content": content
        })

        buffer = ""

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue

        # Điều
        if m := re.match(r"^Điều\s+(\d+)", line):
            flush()
            article = int(m.group(1))
            clause = None
            buffer = line
            continue

        # Khoản
        if m := re.match(r"^(\d+)\.\s+", line):
            flush()
            clause = int(m.group(1))
            buffer = line
            continue

        buffer += "\n" + line

    flush()
    return records


# ===================== STEP 3: SAVE JSON =====================
def save_to_json(law_name, law_year, records):
    output_path = os.path.join(
        OUTPUT_FOLDER,
        f"{law_name}_{law_year}.json"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {"Data": records},
            f,
            ensure_ascii=False,
            indent=2
        )

    return output_path


# ===================== MAIN =====================
if __name__ == "__main__":
    pdf_files = [
        f for f in os.listdir(PDF_FOLDER)
        if f.lower().endswith(".pdf")
    ]

    print(f"Tìm thấy {len(pdf_files)} file PDF\n")

    for fname in pdf_files:
        pdf_path = os.path.join(PDF_FOLDER, fname)
        print(f"Đang xử lý: {fname}")

        try:
            law_name, law_year = parse_law_meta_from_filename(fname)
            raw_text = extract_pdf_text(pdf_path)

            records = parse_law_to_json(raw_text, law_name, law_year)
            out_file = save_to_json(law_name, law_year, records)

            print(f"✔ Xuất JSON: {out_file}")
            print(f"  → {len(records)} đoạn (Điều / Khoản)\n")

        except Exception as e:
            print(f"✖ Lỗi file {fname}: {e}")

    print("Hoàn tất xử lý toàn bộ PDF.")
