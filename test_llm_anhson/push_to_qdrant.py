import json
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# --- CẤU HÌNH ---
QDRANT_URL = "http://160.22.161.120:6333"
COLLECTION_NAME = "industrial_zones_vn"
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

def upload_json_to_qdrant(file_path):
    try:
        client = QdrantClient(url=QDRANT_URL)
        model = SentenceTransformer(MODEL_NAME)
        vector_size = model.get_sentence_embedding_dimension()

        if not client.collection_exists(COLLECTION_NAME):
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

        with open(file_path, 'r', encoding='utf-8') as f:
            full_data = json.load(f)
        
        records = full_data.get("Data", [])
        print(f"Bắt đầu đẩy {len(records)} bản ghi...")

        points = []
        for item in tqdm(records):
            # Tạo văn bản để AI học
            text_input = f"{item.get('Name', '')}. {item.get('Address', '')}"
            vector = model.encode(text_input).tolist()

            points.append(PointStruct(
                id=item["Id"], 
                vector=vector,
                payload=item
            ))

        # Upsert
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print("Thành công!")
        
    except Exception as e:
        print(f"Có lỗi xảy ra: {e}")

if __name__ == "__main__":
    # Đảm bảo file data_ipp.json nằm cùng thư mục với file code này
    upload_json_to_qdrant('C:\\Users\\sonlv\\Downloads\\traningai\\dataIndustrial_2d6e5ca9-40c0-4785-979b-058c76049677.json')