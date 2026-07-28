import os
import sys
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

def run_openai_ingestion():
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: OPENAI_API_KEY not found in backend/.env file.")
        print("Please add OPENAI_API_KEY=your_key_here to your environment.")
        sys.exit(1)

    # Resolve paths
    backend_dir = Path(__file__).resolve().parents[1]
    pdf_path = backend_dir.parent / "constitution_of_india.pdf"
    chroma_db_dir = backend_dir / "chroma_db_openai"

    if not pdf_path.exists():
        print(f"Error: PDF file not found at {pdf_path}")
        sys.exit(1)

    print(f"Loading PDF from: {pdf_path}")
    
    # 1. Load PDF using PyPDFLoader
    from langchain_community.document_loaders import PyPDFLoader
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    print(f"Loaded {len(pages)} pages from the PDF.")

    # 2. Split PDF into chunks (e.g., 500-1000 tokens with overlap)
    from langchain_text_splitters import TokenTextSplitter
    print("Splitting document into token-based chunks...")
    # Using 750 tokens as size (between 500 and 1000) and 100 tokens overlap
    text_splitter = TokenTextSplitter(chunk_size=750, chunk_overlap=100)
    chunks = text_splitter.split_documents(pages)
    print(f"Created {len(chunks)} chunks.")

    # 3. Clear existing Chroma directory to avoid duplicate indexes
    if chroma_db_dir.exists():
        print(f"Clearing existing database directory at {chroma_db_dir}...")
        try:
            shutil.rmtree(chroma_db_dir)
            print("Database directory cleared successfully.")
        except Exception as e:
            print(f"Warning: Could not clear database directory: {e}. Attempting to overwrite.")

    # 4. Generate embeddings and store in Chroma
    print("Generating embeddings using OpenAI Embeddings API and saving to Chroma...")
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=openai_api_key
    )

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(chroma_db_dir)
    )

    print("\n--- Ingestion Summary ---")
    print(f"Total chunks indexed: {len(chunks)}")
    print(f"Chroma DB saved successfully at: {chroma_db_dir}")

if __name__ == "__main__":
    run_openai_ingestion()
