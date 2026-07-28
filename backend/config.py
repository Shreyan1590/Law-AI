import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "./data")
    COLLECTION_NAME: str = "kb_documents"
    
    # RAG Hyperparameters
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    RETRIEVAL_K: int = 4

settings = Settings()