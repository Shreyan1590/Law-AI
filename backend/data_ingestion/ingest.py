import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv()

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# Define path for Chroma persistent storage
CHROMA_DB_DIR = str(Path(__file__).resolve().parents[1] / "chroma_db")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

def inspect_constitution_library():
    """
    Dynamically imports and inspects the indianconstitution library.
    """
    from indianconstitution import Constitution
    ic = Constitution()
    
    print("--- Library Inspection ---")
    print("Preamble type:", type(ic.preamble))
    print("Preamble preview:", ic.preamble[:150])
    
    print("Articles list count:", len(ic.data.articles))
    if ic.data.articles:
        first = ic.data.articles[0]
        print("Article fields:")
        print("Number:", getattr(first, "number", None))
        print("Title:", getattr(first, "title", None))
        print("Part:", getattr(first, "part", None))
        print("Content preview:", getattr(first, "content", "")[:100])

def run_ingestion():
    from indianconstitution import Constitution
    ic = Constitution()
    
    documents = []
    
    # 1. Load Preamble
    try:
        preamble_text = ic.preamble
        if preamble_text:
            documents.append(Document(
                page_content=f"Preamble\n\n{preamble_text}",
                metadata={
                    "type": "preamble", 
                    "title": "Preamble of the Constitution of India", 
                    "number": 0, 
                    "part": "Preamble"
                }
            ))
            print("Preamble loaded.")
    except Exception as e:
        print(f"Warning: Failed to load Preamble: {e}")
        
    # 2. Load Articles
    try:
        articles = ic.data.articles
        loaded_articles_count = 0
        for art in articles:
            art_num = getattr(art, "number", "")
            art_title = getattr(art, "title", "")
            art_content = getattr(art, "content", "")
            art_part = getattr(art, "part", "") or "Unknown Part"
            
            if not art_num or not art_content:
                continue
                
            # Convert article number string (e.g. '1', '21A') to string metadata safely
            metadata = {
                "type": "article",
                "number": str(art_num),
                "title": str(art_title),
                "part": str(art_part)
            }
            
            # Formatting text context clearly for embedding similarity
            content_text = f"Article {art_num}: {art_title}\nPart: {art_part}\n\n{art_content}"
            documents.append(Document(page_content=content_text, metadata=metadata))
            loaded_articles_count += 1
            
        print(f"Loaded {loaded_articles_count} articles.")
    except Exception as e:
        print(f"Error loading articles: {e}")

    if not documents:
        print("Error: No documents were parsed! Please check database ingestion.")
        sys.exit(1)
        
    # 3. Generate Embeddings & Store in Chroma
    print("Generating embeddings and saving to Chroma DB... (This might take a minute)")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    
    # Initialize Chroma persistent DB
    db = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=CHROMA_DB_DIR
    )
    
    # 4. Save to Cloudflare D1 SQL Database
    from rag_pipeline.d1_client import D1Client
    d1 = D1Client()
    d1_success = False
    if d1.is_configured():
        print("Initializing Cloudflare D1 tables...")
        try:
            # Create tables
            d1.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT UNIQUE,
                title TEXT,
                part TEXT,
                content TEXT,
                type TEXT
            );
            """)
            d1.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                timestamp TEXT,
                cited_articles TEXT,
                generated_citations TEXT
            );
            """)
            
            print("Uploading articles to Cloudflare D1 in batches...")
            batch_size = 50
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                placeholders = []
                params = []
                for doc in batch_docs:
                    placeholders.append("(?, ?, ?, ?, ?)")
                    params.extend([
                        str(doc.metadata.get("number", "")),
                        str(doc.metadata.get("title", "")),
                        str(doc.metadata.get("part", "")),
                        str(doc.page_content),
                        str(doc.metadata.get("type", "article"))
                    ])
                sql = f"INSERT OR REPLACE INTO articles (number, title, part, content, type) VALUES {', '.join(placeholders)}"
                d1.execute(sql, params)
                print(f"Uploaded D1 batch {i // batch_size + 1}/{(len(documents) - 1) // batch_size + 1}")
            print("Successfully uploaded all articles to Cloudflare D1!")
            d1_success = True
        except Exception as e:
            print(f"Error ingesting into Cloudflare D1: {e}")
    else:
        print("Cloudflare D1 is not configured. Skipping D1 database initialization.")
        
    print("\n--- Ingestion Summary ---")
    print(f"Total chunks created: {len(documents)}")
    print(f"Articles loaded: {loaded_articles_count}")
    print(f"Chroma DB saved successfully at: {CHROMA_DB_DIR}")
    if d1.is_configured():
        print(f"Cloudflare D1 ingestion: {'SUCCESS' if d1_success else 'FAILED'}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--inspect":
        inspect_constitution_library()
    else:
        run_ingestion()
