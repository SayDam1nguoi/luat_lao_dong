# ===================== IMPORTS =====================
import os
import time
import json
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import Pinecone
from pinecone import Pinecone as PineconeClient, PodSpec


# ===================== CẤU HÌNH =====================
OPENAI_API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME_MSN_2018")

EMBEDDING_DIM = 3072
JSON_FOLDER = r"C:\Users\tabao\OneDrive\Desktop\cong_viec_lam\data_msn_2018"
BATCH_SIZE = 30


# ===================== INIT =====================
print("🔧 Khởi tạo Pinecone & Embedding...")

if not all([
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    PINECONE_API_KEY,
    PINECONE_ENVIRONMENT,
    PINECONE_INDEX_NAME
]):
    raise RuntimeError("❌ Thiếu biến môi trường")

pc = PineconeClient(api_key=PINECONE_API_KEY)

emb = OpenAIEmbeddings(
    api_key=OPENAI_API_KEY,
    model=OPENAI_EMBEDDING_MODEL
)

print("✅ Sẵn sàng\n")


# ===================== UTIL =====================
def get_json_files_from_folder(folder: str) -> List[str]:
    if not os.path.exists(folder):
        return []
    return sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".json")
    )


def create_or_get_index(index_name: str, force: bool = False):
    if force and index_name in pc.list_indexes().names():
        print(f"🗑️ Xóa index {index_name}")
        pc.delete_index(index_name)
        time.sleep(3)

    if index_name not in pc.list_indexes().names():
        print(f"🛠️ Tạo index {index_name}")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=PodSpec(environment=PINECONE_ENVIRONMENT)
        )
        time.sleep(5)

    return pc.Index(index_name)


# ===================== VSIC HELPERS =====================
def detect_level(code: str) -> str:
    """
    Xác định cấp VSIC dựa vào mã
    """
    if not code:
        return "unknown"

    if code.isalpha():
        return "section"      # A, B, C

    if code.isdigit():
        if len(code) == 2:
            return "division"     # 01
        if len(code) == 3:
            return "group"        # 011
        if len(code) == 4:
            return "class"        # 0118
        if len(code) == 5:
            return "subclass"     # 01110

    return "unknown"


# ===================== LOAD JSON (MAPPING) =====================
def load_and_chunk_json(file_path: str) -> List[Dict[str, Any]]:
    """
    JSON dạng mapping phẳng:
    {
        "A": "NÔNG NGHIỆP, LÂM NGHIỆP VÀ THUỶ SẢN",
        "01": "Nông nghiệp và hoạt động dịch vụ có liên quan",
        "01110": "Trồng lúa",
        ...
    }
    """
    filename = os.path.basename(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print(f"⚠️ {filename} không phải JSON object")
            return []

        docs: List[Dict[str, Any]] = []

        for code, name in data.items():
            if not isinstance(name, str):
                continue

            name_clean = name.strip()
            if not name_clean:
                continue

            text = f"Mã ngành {code}: {name_clean}"

            docs.append({
                "text": text,
                "metadata": {
                    "industry_code": code,
                    "industry_name": name_clean,
                    "level": detect_level(code),
                    "source_file": filename
                }
            })

        return docs

    except Exception as e:
        print(f"❌ Lỗi đọc JSON {filename}: {e}")
        return []


# ===================== INGEST =====================
def ingest_documents_to_pinecone(
    json_paths: List[str],
    index_name: str,
    force_reload: bool = False
):
    print("=" * 70)
    print("🚀 INGEST VSIC JSON → PINECONE")
    print("=" * 70)
    print(f"📁 Folder: {JSON_FOLDER}")
    print(f"📚 File JSON: {len(json_paths)}")
    print(f"☁️ Index: {index_name}\n")

    index = create_or_get_index(index_name, force_reload)

    all_docs: List[Dict[str, Any]] = []
    file_stats: Dict[str, int] = {}

    print("📖 Load JSON...\n")

    for path in json_paths:
        filename = os.path.basename(path)
        print(f"📄 {filename}...", end=" ")

        docs = load_and_chunk_json(path)
        if not docs:
            print("✗")
            continue

        all_docs.extend(docs)
        file_stats[filename] = len(docs)
        print(f"✓ {len(docs)} entries")

    if not all_docs:
        raise RuntimeError("❌ Không có document để ingest")

    print(f"\n📦 Tổng vectors: {len(all_docs)}")
    print("💾 Nạp Pinecone...\n")

    vectordb = None
    total_batches = (len(all_docs) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(all_docs), BATCH_SIZE):
        batch = all_docs[i:i + BATCH_SIZE]
        batch_no = (i // BATCH_SIZE) + 1

        print(f"   📦 Batch {batch_no}/{total_batches} ({len(batch)} docs)...", end=" ")

        texts = [d["text"] for d in batch]
        metadatas = [d["metadata"] for d in batch]

        if vectordb is None:
            vectordb = Pinecone.from_texts(
                texts=texts,
                metadatas=metadatas,
                embedding=emb,
                index_name=index_name
            )
        else:
            vectordb.add_texts(
                texts=texts,
                metadatas=metadatas
            )

        print("✓")
        time.sleep(0.5)

    stats = index.describe_index_stats()

    print("\n" + "=" * 70)
    print("📊 KẾT QUẢ")
    print("=" * 70)
    print(f"✅ Tổng vectors trong index: {stats['total_vector_count']}")
    print(f"📁 File xử lý: {len(file_stats)}")
    for f, c in file_stats.items():
        print(f"   • {f}: {c} vectors")
    print("=" * 70)


# ===================== MAIN =====================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser("Ingest VSIC JSON → Pinecone")
    parser.add_argument("--force-reload", action="store_true")
    parser.add_argument("--folder", type=str, default=JSON_FOLDER)

    args = parser.parse_args()

    json_files = get_json_files_from_folder(args.folder)

    if not json_files:
        raise RuntimeError("❌ Không tìm thấy file JSON")

    print(f"📄 Tìm thấy {len(json_files)} file JSON:")
    for i, f in enumerate(json_files, 1):
        print(f"   {i}. {os.path.basename(f)}")
    print()

    ingest_documents_to_pinecone(
        json_paths=json_files,
        index_name=PINECONE_INDEX_NAME,
        force_reload=args.force_reload
    )

    print("\n🎉 HOÀN THÀNH")
