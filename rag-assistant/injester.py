import os
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from config import settings

def get_vector_store() -> Chroma:
    """Returns persistent ChromaDB instance."""
    embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
    return Chroma(
        collection_name=settings.COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_PERSIST_DIR
    )

def ingest_documents(docs_dir: str = settings.DOCUMENTS_DIR) -> int:
    """Loads, splits, and embeds all files from the documents directory."""
    dir_path = Path(docs_dir)
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        return 0

    documents = []
    
    # Load TXT files
    txt_loader = DirectoryLoader(docs_dir, glob="**/*.txt", loader_cls=TextLoader)
    documents.extend(txt_loader.load())
    
    # Load PDF files
    pdf_loader = DirectoryLoader(docs_dir, glob="**/*.pdf", loader_cls=PyPDFLoader)
    documents.extend(pdf_loader.load())

    if not documents:
        return 0

    # Split documents into chunks with context overlap
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)

    # Persist to ChromaDB
    embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=settings.COLLECTION_NAME,
        persist_directory=settings.CHROMA_PERSIST_DIR
    )

    return len(chunks)

if __name__ == "__main__":
    count = ingest_documents()
    print(f"Ingested {count} document chunks into ChromaDB.")