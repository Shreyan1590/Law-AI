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
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CONSTITUTION_PDF_PATH = str(DATA_DIR / "constitution_of_india.pdf")
BNS_PDF_PATH = str(DATA_DIR / "BNS.pdf")
BNSS_PDF_PATH = str(DATA_DIR / "BNSS.pdf")
BSA_PDF_PATH = str(DATA_DIR / "BSA.pdf")

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

def parse_constitution(pdf_path) -> list[Document]:
    print(f"Opening Constitution PDF: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    # 1. Load Preamble (Page 31)
    preamble_text = ""
    try:
        p31_text = reader.pages[31].extract_text() or ""
        if "PREAMBLE" in p31_text:
            preamble_text = p31_text.split("PREAMBLE")[-1].strip()
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
        
    # 2. Extract and concatenate Articles text (Pages 32 to 282 inclusive)
    articles_full_text = ""
    for page_idx in range(32, 283):
        if page_idx >= total_pages:
            break
        page_text = reader.pages[page_idx].extract_text() or ""
        cleaned_page = clean_extracted_text(page_text)
        articles_full_text += "\n" + cleaned_page
        
    # 3. Parse Articles and Parts
    article_pattern = re.compile(
        r'\n\s*(\d+[A-Z]?)\.\s+([A-Za-z0-9\s,⎯—–\-\(\)/\"”’‘\'“”]+)(?:\.—|\.\s*—|\.\s*–|\.\s*⎯)'
    )
    
    matches = list(article_pattern.finditer(articles_full_text))
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
        
    for i, match in enumerate(matches):
        art_num = match.group(1)
        art_title = match.group(2).strip()
        start_pos = match.end()
        if i + 1 < len(matches):
            end_pos = matches[i + 1].start()
        else:
            end_pos = len(articles_full_text)
            
        art_content = articles_full_text[start_pos:end_pos].strip()
        art_content = re.split(r'\bPART\s+[IVXLCDM]+\b', art_content)[0].strip()
        art_part = get_part_for_position(match.start())
        
        metadata = {
            "type": "article",
            "number": str(art_num),
            "title": str(art_title),
            "part": str(art_part),
            "article": f"Article {art_num}",
            "source": "Constitution of India"
        }
        
        content_text = f"Article {art_num}: {art_title}\n{art_part}\n\n{art_content}"
        documents.append(Document(page_content=content_text, metadata=metadata))
        
    print(f"Constitution parsed: {len(documents)} segments.")
    return documents

def get_section_title(sec_text, sec_num, source_name):
    # Clean first line
    lines = [l.strip() for l in sec_text.split('\n') if l.strip()]
    if not lines:
        return f"Section {sec_num}"
    
    # Remove the section number prefix (e.g., "15.")
    first_line = lines[0]
    first_line_clean = re.sub(r'^\d+\.[\s\xa0]*', '', first_line).strip()
    
    # Take the first sentence or first 80 characters
    first_sentence = first_line_clean.split('.')[0].strip()
    # Remove sub-section markers like (1) from start
    first_sentence = re.sub(r'^\(\d+\)\s*', '', first_sentence).strip()
    if len(first_sentence) > 80:
        first_sentence = first_sentence[:77] + "..."
    if not first_sentence:
        first_sentence = f"Section {sec_num} of {source_name}"
    return first_sentence

def parse_criminal_code(pdf_path: str, prefix: str, source_name: str) -> list[Document]:
    print(f"Opening Criminal Code PDF: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    full_text = "\n".join([page.extract_text() or "" for page in reader.pages])
    
    section_pattern = r'\n(?=\s*\d+\.(?:\s*|\([^\)]+\)\s*)[A-Z\(\"“\'])'
    raw_chunks = re.split(section_pattern, full_text)
    
    # Parse Chapters to associate sections with their respective Chapters
    chapter_pattern = re.compile(r'\bCHAPTER\s+([IVXLCDM]+)\s*\n\s*([^\n]+)', re.IGNORECASE)
    chapters_list = list(chapter_pattern.finditer(full_text))
    
    def get_chapter_for_position(pos):
        current_chapter = "General"
        for chap_match in chapters_list:
            if chap_match.start() < pos:
                current_chapter = f"Chapter {chap_match.group(1)}: {chap_match.group(2).strip()}"
            else:
                break
        return current_chapter

    # Find the positions of the chunks in the full text to assign correct chapters
    documents = []
    current_pos = 0
    
    for idx, chunk in enumerate(raw_chunks):
        text = chunk.strip()
        if not text:
            continue
        
        # Locate chunk position in full text
        pos = full_text.find(chunk, current_pos)
        if pos != -1:
            current_pos = pos + len(chunk)
        else:
            pos = current_pos
            
        # Extract section number (e.g. "98.Whoever" or "105. Whoever")
        first_line = text.split('\n')[0].strip()
        match = re.match(r'^\s*(\d+)\.', first_line)
        if not match:
            match = re.search(r'\b(\d+)\.', first_line)
            
        if match:
            sec_num = match.group(1)
            # Create a unique number like "BNS Section 15"
            number_val = f"{prefix} Section {sec_num}"
            title_val = get_section_title(text, sec_num, source_name)
            part_val = get_chapter_for_position(pos)
            
            metadata = {
                "type": "article",  # type is "article" so export script picks it up
                "number": number_val,
                "title": title_val,
                "part": part_val,
                "article": number_val,
                "source": source_name
            }
            
            content_text = f"{number_val}: {title_val}\n{part_val}\n\n{text}"
            documents.append(Document(page_content=content_text, metadata=metadata))
            
    print(f"Parsed {source_name}: {len(documents)} segments.")
    return documents

def run_pdf_ingestion():
    documents = []
    
    # 1. Parse Constitution
    if os.path.exists(CONSTITUTION_PDF_PATH):
        documents.extend(parse_constitution(CONSTITUTION_PDF_PATH))
    else:
        print(f"Warning: Constitution PDF not found at {CONSTITUTION_PDF_PATH}")

    # 2. Parse BNS
    if os.path.exists(BNS_PDF_PATH):
        documents.extend(parse_criminal_code(BNS_PDF_PATH, "BNS", "Bharatiya Nyaya Sanhita (BNS)"))
    else:
        print(f"Warning: BNS PDF not found at {BNS_PDF_PATH}")
        
    # 3. Parse BNSS
    if os.path.exists(BNSS_PDF_PATH):
        documents.extend(parse_criminal_code(BNSS_PDF_PATH, "BNSS", "Bharatiya Nagarik Suraksha Sanhita (BNSS)"))
    else:
        print(f"Warning: BNSS PDF not found at {BNSS_PDF_PATH}")
        
    # 4. Parse BSA
    if os.path.exists(BSA_PDF_PATH):
        documents.extend(parse_criminal_code(BSA_PDF_PATH, "BSA", "Bharatiya Sakshya Adhiniyam (BSA)"))
    else:
        print(f"Warning: BSA PDF not found at {BSA_PDF_PATH}")

    if not documents:
        print("Error: No documents were parsed! Please check PDF paths.")
        sys.exit(1)
        
    print(f"Total documents prepared for database: {len(documents)}")
    
    # Delete the existing Chroma database directory to clear any duplicates
    if os.path.exists(CHROMA_DB_DIR):
        print(f"Clearing existing database directory at {CHROMA_DB_DIR} to avoid duplicates...")
        try:
            shutil.rmtree(CHROMA_DB_DIR)
            print("Database directory cleared successfully.")
        except Exception as e:
            print(f"Warning: Could not clear database directory: {e}. Trying to overwrite.")
            
    # 4. Generate Embeddings & Save to Chroma DB (Overwriting previous database)
    print("Generating embeddings from PDFs and updating Chroma DB... (This will take a moment)")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    
    from config import settings
    db = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=settings.COLLECTION_NAME,
        persist_directory=CHROMA_DB_DIR,
        collection_metadata={"hnsw:space": "cosine"}
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
        finally:
            # Sleep brief moment to allow D1 to finalize writes
            import time
            time.sleep(1)
    else:
        print("Cloudflare D1 is not configured. Skipping D1 database initialization.")
        
    print("\n--- Ingestion Summary ---")
    print(f"Total chunks created: {len(documents)}")
    print(f"Chroma DB saved successfully at: {CHROMA_DB_DIR}")
    if d1.is_configured():
        print(f"Cloudflare D1 ingestion: {'SUCCESS' if d1_success else 'FAILED'}")

if __name__ == "__main__":
    run_pdf_ingestion()
