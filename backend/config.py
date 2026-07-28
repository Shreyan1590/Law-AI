import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    DOCUMENTS_DIR: str = os.getenv("DOCUMENTS_DIR", "./data")
    COLLECTION_NAME: str = "kb_documents"
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "huggingface")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    
    # RAG Hyperparameters
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    RETRIEVAL_K: int = 4

settings = Settings()