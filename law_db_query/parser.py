import re
import unicodedata

def normalize_law_name(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()

    stopwords = {"luat"}
    words = [w for w in text.split() if w not in stopwords]

    return "".join(w.capitalize() for w in words)


def generate_law_name_variants(law_raw: str):
    base = normalize_law_name(law_raw)
    variants = {base}

    if not base.startswith("Bo"):
        variants.add("Bo" + base)

    return list(variants)


def parse_law_query(message: str):
    m_article = re.search(r"điều\s+(\d+)", message, re.IGNORECASE)
    m_law = re.search(r"luật\s+(.+)", message, re.IGNORECASE)

    if not m_article or not m_law:
        raise ValueError("Không parse được câu hỏi luật")

    article = int(m_article.group(1))
    law_variants = generate_law_name_variants(m_law.group(1))

    return law_variants, article
