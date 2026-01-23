# ================= ai_rag_system.py =================
import httpx
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# ===================== CONFIG =====================
QDRANT_URL = "http://160.22.161.120:6333"
COLLECTION_NAME = "vietnam_laws"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
TOP_K = 3

# ===================== INIT =====================
print("Kết nối Qdrant...")
client = QdrantClient(
    url=QDRANT_URL,
    timeout=60,
    check_compatibility=False
)

print("Load embedding model...")
model = SentenceTransformer(MODEL_NAME)

# ===================== SEARCH (HTTP /points/search - COMPAT) =====================
def search_law_y_te(question: str) -> str:
    """
    Search LUẬT Y TẾ bằng HTTP endpoint /points/search (tương thích Qdrant server cũ/mới)
    """
    query_vector = model.encode(question).tolist()

    url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search"
    payload = {
        "vector": query_vector,
        "limit": TOP_K,
        "with_payload": True
    }

    r = httpx.post(url, json=payload, timeout=60)
    r.raise_for_status()

    data = r.json() or {}
    points = data.get("result") or []

    if not points:
        return "Không tìm thấy quy định pháp luật y tế phù hợp."

    answers = []
    for p in points:
        payload = p.get("payload") or {}
        answers.append(
            f"📘 {payload.get('LawName')} {payload.get('LawYear')} – "
            f"Điều {payload.get('Article')}, Khoản {payload.get('Clause')}:\n"
            f"{payload.get('Content')}"
        )

    return "\n\n".join(answers)

# ===================== CLI =====================
if __name__ == "__main__":
    print("\nHỏi về LUẬT Y TẾ (gõ 'exit' để thoát)\n")

    while True:
        q = input("❓ Câu hỏi: ").strip()
        if q.lower() in {"exit", "quit"}:
            break

        print("\n--- KẾT QUẢ ---")
        print(search_law_y_te(q))
        print("----------------\n")
