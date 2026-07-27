import os
import sys
import re
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv()

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import pypdf

# Define path for Chroma persistent storage
CHROMA_DB_DIR = str(Path(__file__).resolve().parents[1] / "chroma_db")
PDF_PATH = str(Path(__file__).resolve().parents[1].parent / "constitution_of_india.pdf")

def clean_extracted_text(text):
    """
    Cleans up common header/footer line patterns, page numbers, and formatting issues.
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Remove empty lines
        if not stripped:
            continue
        # Remove common header running title
        if "THE CONSTITUTION OF INDIA" in stripped:
            continue
        # Remove Part headers in parentheses like (Part I.—Union and its territory)
        if re.search(r'\(Part\s+[IVXLCDM]+\..*?\)', stripped, re.IGNORECASE):
            continue
        # Remove raw page numbers at the very bottom (typically single/double/triple digits on their own line)
        if re.match(r'^\d+$', stripped):
            continue
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def run_pdf_ingestion():
    if not os.path.exists(PDF_PATH):
        print(f"Error: PDF file not found at {PDF_PATH}")
        sys.exit(1)
        
    print(f"Opening PDF file: {PDF_PATH}")
    reader = pypdf.PdfReader(PDF_PATH)
    total_pages = len(reader.pages)
    print(f"Total PDF pages: {total_pages}")
    
    # 1. Load Preamble (Page 31)
    preamble_text = ""
    try:
        # Page 31 in 0-based index is page index 31
        p31_text = reader.pages[31].extract_text() or ""
        if "PREAMBLE" in p31_text:
            # Clean and extract text from PREAMBLE onwards
            preamble_text = p31_text.split("PREAMBLE")[-1].strip()
            # Remove footnotes from the bottom of the preamble page
            preamble_text = re.split(r'\n\s*1\.\s+Subs\b', preamble_text)[0].strip()
    except Exception as e:
        print(f"Warning: Failed to extract Preamble from page 31: {e}")
        
    documents = []
    if preamble_text:
        documents.append(Document(
            page_content=f"Preamble\n\n{preamble_text}",
            metadata={
                "type": "preamble",
                "title": "Preamble of the Constitution of India",
                "number": "0",
                "part": "Preamble"
            }
        ))
        print("Preamble loaded from PDF.")
        
    # 2. Extract and concatenate Articles text (Pages 32 to 282 inclusive)
    print("Extracting text from Article pages (32 to 282)...")
    articles_full_text = ""
    
    for page_idx in range(32, 283):
        if page_idx >= total_pages:
            break
        page_text = reader.pages[page_idx].extract_text() or ""
        # Clean page-level headers/footers
        cleaned_page = clean_extracted_text(page_text)
        articles_full_text += "\n" + cleaned_page
        
    # 3. Parse Articles and Parts
    # We will look for:
    # A) Part headers: "PART I", "PART II", etc. followed by the part title
    # B) Articles: e.g. "1. Name and territory of the Union.—"
    
    # Regex to find starting positions of articles
    # Pattern: \n followed by number (with optional letter like 21A), period, title, and em-dash/en-dash punctuation
    article_pattern = re.compile(
        r'\n\s*(\d+[A-Z]?)\.\s+([A-Za-z0-9\s,⎯—–\-\(\)/\"”’‘\'“”]+)(?:\.—|\.\s*—|\.\s*–|\.\s*⎯)'
    )
    
    # Find all article matches and their spans
    matches = list(article_pattern.finditer(articles_full_text))
    print(f"Found {len(matches)} articles in the PDF text.")
    
    # We will scan the text to identify Part divisions and attach the part name to metadata
    part_pattern = re.compile(r'\bPART\s+([IVXLCDM]+)\s*\n\s*([^\n]+)', re.IGNORECASE)
    parts_list = list(part_pattern.finditer(articles_full_text))
    
    def get_part_for_position(pos):
        current_part = "Unknown Part"
        for part_match in parts_list:
            if part_match.start() < pos:
                current_part = f"Part {part_match.group(1)}: {part_match.group(2).strip()}"
            else:
                break
        return current_part
        
    # Slice the concatenated text by matches to extract the full body of each article
    for i, match in enumerate(matches):
        art_num = match.group(1)
        art_title = match.group(2).strip()
        
        # Start of this article body is right after the heading match ends
        start_pos = match.end()
        
        # End of this article body is the start of the next article match (or end of document)
        if i + 1 < len(matches):
            end_pos = matches[i + 1].start()
        else:
            end_pos = len(articles_full_text)
            
        art_content = articles_full_text[start_pos:end_pos].strip()
        
        # Clean any trailing Part headers or numbers at the end of the text slice
        art_content = re.split(r'\bPART\s+[IVXLCDM]+\b', art_content)[0].strip()
        
        # Determine which Part this article belongs to based on its position in the text
        art_part = get_part_for_position(match.start())
        
        metadata = {
            "type": "article",
            "number": str(art_num),
            "title": str(art_title),
            "part": str(art_part)
        }
        
        content_text = f"Article {art_num}: {art_title}\n{art_part}\n\n{art_content}"
        documents.append(Document(page_content=content_text, metadata=metadata))
        
    print(f"Total documents prepared for database: {len(documents)}")
    
    if len(documents) <= 1:
        print("Error: Parsing failed to yield articles! Database will not be updated.")
        sys.exit(1)
        
    # Delete the existing Chroma database directory to clear any duplicates
    if os.path.exists(CHROMA_DB_DIR):
        print(f"Clearing existing database directory at {CHROMA_DB_DIR} to avoid duplicates...")
        try:
            shutil.rmtree(CHROMA_DB_DIR)
            print("Database directory cleared successfully.")
        except Exception as e:
            print(f"Warning: Could not clear database directory: {e}. Trying to overwrite.")
            
    # 4. Generate Embeddings & Save to Chroma DB (Overwriting previous database)
    print("Generating embeddings from PDF and updating Chroma DB... (This will take a moment)")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    
    db = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=CHROMA_DB_DIR
    )
    
    # 5. Save to Cloudflare D1 SQL Database
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
        
    print("\n--- PDF Ingestion Summary ---")
    print(f"Total chunks created: {len(documents)}")
    print(f"Chroma DB saved successfully at: {CHROMA_DB_DIR}")
    if d1.is_configured():
        print(f"Cloudflare D1 ingestion: {'SUCCESS' if d1_success else 'FAILED'}")

if __name__ == "__main__":
    run_pdf_ingestion()
