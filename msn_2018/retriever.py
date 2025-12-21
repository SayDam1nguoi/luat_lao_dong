import os
from pinecone import Pinecone as PineconeClient
from langchain_pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings


def load_vsic_2018_retriever(embedding: OpenAIEmbeddings):
    """
    Load Pinecone retriever cho VSIC 2018
    """
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME_MSN_2018")

    if not pinecone_api_key or not index_name:
        raise RuntimeError("Thiếu cấu hình Pinecone cho VSIC 2018")

    pc = PineconeClient(api_key=pinecone_api_key)

    if index_name not in pc.list_indexes().names():
        raise RuntimeError(f"Pinecone index VSIC 2018 '{index_name}' không tồn tại")

    index = pc.Index(index_name)
    stats = index.describe_index_stats()

    if stats["total_vector_count"] == 0:
        raise RuntimeError("Pinecone index VSIC 2018 rỗng")

    vectordb = Pinecone(
        index=index,
        embedding=embedding,
        text_key="text"
    )

    retriever = vectordb.as_retriever(search_kwargs={"k": 10})
    return retriever
