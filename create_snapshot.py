import os
import json
import uuid
import shutil

from dotenv import load_dotenv
from pypdf import PdfReader
from openai import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
import chromadb
from chromadb.config import Settings

# =====================================================
# LOAD ENV
# =====================================================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI__API_KEY")
EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")

if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI__API_KEY chưa được set trong file .env")

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================
# CHROMA CONFIG (QUAN TRỌNG)
# =====================================================
PERSIST_DIR = "./chroma_data"
COLLECTION_NAME = "pdf_collection"

chroma_client = chromadb.Client(
    Settings(
        persist_directory=PERSIST_DIR,
        anonymized_telemetry=False
    )
)

collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME
)

# =====================================================
# STEP 1: LOAD PDF
# =====================================================
def load_pdf_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    if not text.strip():
        raise ValueError("❌ PDF không trích xuất được text")
    return text

# =====================================================
# STEP 2: SPLIT TEXT
# =====================================================
def split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )
    chunks = splitter.split_text(text)
    if not chunks:
        raise ValueError("❌ Không tạo được chunk")
    return chunks

# =====================================================
# STEP 3: EMBEDDING (BATCH SAFE)
# =====================================================
def embed_texts(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )

        embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(embeddings)

        print(f"🧠 Embedded {len(all_embeddings)}/{len(texts)} chunks")

    return all_embeddings

# =====================================================
# STEP 4: ADD TO CHROMA
# =====================================================
def add_to_chroma(chunks, embeddings, pdf_path):
    ids = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        ids.append(str(uuid.uuid4()))
        metadatas.append({
            "chunk_index": i,
            "source_pdf": os.path.basename(pdf_path)
        })

    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas
    )

# =====================================================
# STEP 5: CREATE SNAPSHOT ZIP (UPLOAD ĐƯỢC)
# =====================================================
def create_snapshot_zip(output_zip="chroma_snapshot.zip"):
    # ChromaDB đã tự persist vào persist_directory
    if os.path.exists(output_zip):
        os.remove(output_zip)

    shutil.make_archive(
        base_name=output_zip.replace(".zip", ""),
        format="zip",
        root_dir=PERSIST_DIR
    )

    print(f"✅ Snapshot Chroma đã tạo: {output_zip}")

# =====================================================
# MAIN PIPELINE
# =====================================================
def create_snapshot_from_pdf(pdf_path: str):
    print("📄 Đang đọc PDF...")
    text = load_pdf_text(pdf_path)

    print("✂️ Đang chia chunk...")
    chunks = split_text(text)
    print(f"📦 Tổng chunk: {len(chunks)}")

    print("🧠 Đang embedding...")
    embeddings = embed_texts(chunks)

    print("📥 Đang lưu vào ChromaDB...")
    add_to_chroma(chunks, embeddings, pdf_path)

    print("💾 Đang tạo snapshot zip...")
    create_snapshot_zip()

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    PDF_PATH = r"C:\Users\tabao\Downloads\27_2018_QD-TTg_387358.pdf"
    create_snapshot_from_pdf(PDF_PATH)
