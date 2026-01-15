# ================= push_law_to_qdrant_batch_safe.py =================
import json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ===================== CONFIG =====================
QDRANT_URL = "http://160.22.161.120:6333"
COLLECTION_NAME = "vietnam_laws"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

BATCH_SIZE = 50          # ❗ quan trọng
REQUEST_TIMEOUT = 120.0  # seconds

# ===================== MAIN =====================
def upload_law_json_to_qdrant(json_path: str):

    print("Kết nối Qdrant...")
    client = QdrantClient(
        url=QDRANT_URL,
        timeout=REQUEST_TIMEOUT,
        check_compatibility=False  # ❗ FIX version mismatch
    )

    print("Load embedding model...")
    model = SentenceTransformer(MODEL_NAME)
    vector_size = model.get_sentence_embedding_dimension()

    if not client.collection_exists(COLLECTION_NAME):
        print(f"Tạo collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            ),
        )

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f).get("Data", [])

    print(f"Tổng số đoạn luật: {len(records)}")

    # ===================== TẠO POINTS =====================
    all_points = []
    for item in records:
        text_input = (
            f"Luật {item.get('LawName')} {item.get('LawYear')}. "
            f"Điều {item.get('Article')}, "
            f"Khoản {item.get('Clause')}. "
            f"{item.get('Content')}"
        )

        vector = model.encode(text_input).tolist()

        all_points.append(
            PointStruct(
                id=item["Id"],
                vector=vector,
                payload=item
            )
        )

    # ===================== UPSERT THEO BATCH =====================
    print("Bắt đầu upsert theo batch...")

    for i in tqdm(range(0, len(all_points), BATCH_SIZE)):
        batch = all_points[i:i + BATCH_SIZE]

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )

    print("✅ Đã đẩy LUẬT lên Qdrant thành công!")

# ===================== ENTRY =====================
if __name__ == "__main__":
    JSON_PATH = r"C:\Users\tabao\OneDrive\Desktop\test_llm_anhson\json_output\Bao Hiem Xa Hoi_2024.json"
    upload_law_json_to_qdrant(JSON_PATH)
