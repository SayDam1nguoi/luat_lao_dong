import os
import time
import json
from typing import List, Dict

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import Pinecone
from pinecone import Pinecone as PineconeClient, PodSpec

# ============================================================
# CONFIG
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

EMBEDDING_DIM = 3072
JSON_PATH = r"C:\Users\tabao\OneDrive\Desktop\cong_viec_lam\pdf_official.json"
BATCH_SIZE = 20

# ============================================================
# CHECK ENV
# ============================================================
if not all([
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    PINECONE_API_KEY,
    PINECONE_ENVIRONMENT,
    PINECONE_INDEX_NAME
]):
    raise RuntimeError("❌ Thiếu biến môi trường")

# ============================================================
# INIT
# ============================================================
print("🔧 Khởi tạo Pinecone & Embedding")

pc = PineconeClient(api_key=PINECONE_API_KEY)
emb = OpenAIEmbeddings(
    api_key=OPENAI_API_KEY,
    model=OPENAI_EMBEDDING_MODEL
)

# ============================================================
# INDEX
# ============================================================
def create_or_get_index(index_name: str, force_recreate=False):
    if force_recreate and index_name in pc.list_indexes().names():
        pc.delete_index(index_name)
        time.sleep(5)

    if index_name not in pc.list_indexes().names():
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=PodSpec(environment=PINECONE_ENVIRONMENT)
        )
        time.sleep(5)

    return pc.Index(index_name)

# ============================================================
# LOAD SECTIONS
# ============================================================
def load_sections(json_path: str) -> List[Dict]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "sections" not in data:
        raise ValueError("❌ JSON không có key 'sections'")

    docs = []

    for sec in data["sections"]:
        content = sec.get("content", "").strip()
        if not content:
            continue

        title = sec.get("title", "").strip()
        sec_id = sec.get("id", "")

        # -------- TEXT EMBEDDING --------
        text = f"{sec_id}. {title}\n\n{content}"

        # -------- METADATA (PINECONE SAFE) --------
        metadata = {
            "source": os.path.basename(json_path),
            "section_id": sec_id,
            "title": title,
            "level": sec_id.count(".") + 1 if sec_id != "LỜI NÓI ĐẦU" else 0
        }

        docs.append({
            "text": text,
            "metadata": metadata
        })

    return docs

# ============================================================
# INGEST
# ============================================================
def ingest(force_reload=False):
    print("=" * 70)
    print("🚀 INGEST STRUCTURED SECTIONS → PINECONE")
    print("=" * 70)

    index = create_or_get_index(PINECONE_INDEX_NAME, force_reload)

    docs = load_sections(JSON_PATH)
    print(f"📦 Tổng số section: {len(docs)}\n")

    vectordb = None
    total_batches = (len(docs) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        batch_no = (i // BATCH_SIZE) + 1

        print(f"📦 Batch {batch_no}/{total_batches} ({len(batch)})...", end=" ")

        if i == 0:
            vectordb = Pinecone.from_texts(
                texts=[d["text"] for d in batch],
                metadatas=[d["metadata"] for d in batch],
                embedding=emb,
                index_name=PINECONE_INDEX_NAME
            )
        else:
            vectordb.add_texts(
                texts=[d["text"] for d in batch],
                metadatas=[d["metadata"] for d in batch]
            )

        print("✓")
        time.sleep(1)

    stats = index.describe_index_stats()

    print("\n" + "=" * 70)
    print("📊 HOÀN THÀNH")
    print("=" * 70)
    print(f"✓ Tổng vectors: {stats['total_vector_count']}")
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force-reload", action="store_true")
    args = parser.parse_args()

    ingest(force_reload=args.force_reload)

    print("\n🎉 INGEST THÀNH CÔNG")
