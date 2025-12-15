# ===================== IMPORTS =====================
import os
import time
import json
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import Pinecone 
from pinecone import Pinecone as PineconeClient, PodSpec

# ===================== CẤU HÌNH =====================
OPENAI_API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

EMBEDDING_DIM = 3072  
JSON_FOLDER = r"C:\Users\tabao\OneDrive\Desktop\cong_viec_lam\json"
BATCH_SIZE = 30  

# ===================== KHỞI TẠO =====================
print("🔧 Đang khởi tạo Pinecone Client và Embedding...")

if not all([OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME]):
    print("❌ LỖI: Thiếu biến môi trường bắt buộc!")
    exit(1)

pc = PineconeClient(api_key=PINECONE_API_KEY)
emb = OpenAIEmbeddings(api_key=OPENAI_API_KEY, model=OPENAI_EMBEDDING_MODEL)

print("✅ Đã khởi tạo thành công!\n")

# ===================== HÀM HỖ TRỢ =====================

def get_json_files_from_folder(folder_path: str) -> List[str]:
    """Lấy tất cả file JSON trong folder."""
    if not os.path.exists(folder_path):
        print(f"⚠️ Folder không tồn tại: {folder_path}")
        return []
    
    json_files = []
    for file in os.listdir(folder_path):
        if file.lower().endswith(".json"):
            json_files.append(os.path.join(folder_path, file))
    
    return sorted(json_files)


def get_existing_sources_from_index(index_name: str) -> set:
    """Lấy danh sách file đã có trong Index."""
    try:
        if index_name not in pc.list_indexes().names():
            return set()
        
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        
        if stats["total_vector_count"] == 0:
            return set()

        dummy_query = [0.0] * EMBEDDING_DIM
        results = index.query(
            vector=dummy_query,
            top_k=50,
            include_metadata=True
        )
        
        sources = set()
        for match in results.get("matches", []):
            if "metadata" in match and "source" in match["metadata"]:
                sources.add(match["metadata"]["source"])
        
        return sources
    
    except Exception as e:
        print(f"⚠️ Lỗi khi lấy danh sách file từ Index: {e}")
        return set()


def create_or_get_index(index_name: str, force_recreate: bool = False):
    """Tạo hoặc lấy Pinecone Index."""
    
    if force_recreate:
        print(f"🗑️ Đang xóa Index '{index_name}' (nếu tồn tại)...")
        if index_name in pc.list_indexes().names():
            pc.delete_index(index_name)
            print(f"✅ Đã xóa Index '{index_name}'")
            time.sleep(3)

    if index_name not in pc.list_indexes().names():
        print(f"🛠️ Đang tạo Index '{index_name}'...")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=PodSpec(environment=PINECONE_ENVIRONMENT)
        )
        print(f"✅ Đã tạo Index '{index_name}'")
        time.sleep(5)

    return pc.Index(index_name)


def load_and_chunk_json(file_path: str) -> List[Dict[str, Any]]:
    """Đọc file JSON và tạo các document để nạp vào Pinecone."""
    filename = os.path.basename(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        docs = []
        for code, desc in data.items():
            text = f"{code}: {desc}"

            docs.append({
                "text": text,
                "metadata": {
                    "source": filename,
                    "code": code
                }
            })

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=0
        )

        final_docs = []
        for doc in docs:
            chunks = splitter.split_text(doc["text"])
            for i, chunk in enumerate(chunks):
                final_docs.append({
                    "text": chunk,
                    "metadata": {**doc["metadata"], "chunk_id": i}
                })

        return final_docs

    except Exception as e:
        print(f"❌ Lỗi khi load JSON {filename}: {e}")
        return []


def ingest_documents_to_pinecone(
    json_paths: List[str],
    index_name: str,
    force_reload: bool = False
):
    print("="*70)
    print("🚀 BẮT ĐẦU NẠP DỮ LIỆU JSON VÀO PINECONE")
    print("="*70)
    print(f"📁 Folder: {JSON_FOLDER}")
    print(f"📚 Tổng số file JSON: {len(json_paths)}")
    print(f"☁️ Index: {index_name}")
    print()

    index = create_or_get_index(index_name, force_recreate=force_reload)

    if not force_reload:
        existing_sources = get_existing_sources_from_index(index_name)
        print(f"📊 File đã có trong Index: {len(existing_sources)}")
    else:
        existing_sources = set()

    target_files = {os.path.basename(p): p for p in json_paths}

    if force_reload:
        files_to_load = target_files
    else:
        files_to_load = {
            n: p for n, p in target_files.items()
            if n not in existing_sources
        }

    print(f"📥 Sẽ nạp {len(files_to_load)} file mới.\n")

    all_docs = []
    file_stats = {}

    for filename, path in files_to_load.items():
        print(f"📄 {filename}...", end=" ")
        docs = load_and_chunk_json(path)

        if docs:
            all_docs.extend(docs)
            file_stats[filename] = len(docs)
            print(f"✓ {len(docs)} docs")
        else:
            print("✗ Lỗi")

    if not all_docs:
        print("❌ Không có document nào để nạp!")
        return

    print(f"\n📦 Tổng cộng {len(all_docs)} docs\n")

    print("💾 Đang nạp vào Pinecone...\n")
    total_batches = (len(all_docs) + BATCH_SIZE - 1) // BATCH_SIZE
    vectordb = None

    try:
        for i in range(0, len(all_docs), BATCH_SIZE):
            batch_docs = all_docs[i:i+BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1

            print(f"   📦 Batch {batch_num}/{total_batches} ({len(batch_docs)} docs)...", end=" ")

            if i == 0:
                vectordb = Pinecone.from_texts(
                    texts=[doc["text"] for doc in batch_docs],
                    metadatas=[doc["metadata"] for doc in batch_docs],
                    embedding=emb,
                    index_name=index_name
                )
            else:
                vectordb.add_texts(
                    texts=[doc["text"] for doc in batch_docs],
                    metadatas=[doc["metadata"] for doc in batch_docs]
                )

            print("✓")
            time.sleep(1)

    except Exception as e:
        print(f"\n❌ Lỗi khi nạp vào Pinecone: {e}")
        return

    stats = index.describe_index_stats()

    print("\n" + "="*70)
    print("📊 KẾT QUẢ CUỐI")
    print("="*70)
    print(f"   ✓ Tổng vectors: {stats['total_vector_count']}")
    print(f"   ✓ File xử lý: {len(file_stats)}")
    for filename, ct in file_stats.items():
        print(f"   • {filename}: {ct} docs")
    print("="*70)


# ===================== MAIN =====================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Nạp file JSON vào Pinecone Index"
    )
    parser.add_argument(
        "--force-reload",
        action="store_true",
        help="Xóa và nạp lại toàn bộ Index"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=JSON_FOLDER,
        help=f"Đường dẫn folder chứa JSON (mặc định: {JSON_FOLDER})"
    )

    args = parser.parse_args()

    json_files = get_json_files_from_folder(args.folder)

    if not json_files:
        print("❌ Không tìm thấy file JSON nào.")
        exit(1)

    print(f"📄 Tìm thấy {len(json_files)} file JSON:")
    for i, fpath in enumerate(json_files, 1):
        print(f"   {i}. {os.path.basename(fpath)}")
    print()

    ingest_documents_to_pinecone(
        json_paths=json_files,
        index_name=PINECONE_INDEX_NAME,
        force_reload=args.force_reload
    )

    print("\n🎉 HOÀN THÀNH!")
