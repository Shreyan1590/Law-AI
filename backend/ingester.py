import os
import re
import shutil
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from config import settings

def clean_constitution_text(text):
    """
    Cleans up common header/footer line patterns, page numbers, and formatting issues for the Constitution.
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Remove common header running title
        if "THE CONSTITUTION OF INDIA" in stripped:
            continue
        # Remove Part headers in parentheses like (Part I.—Union and its territory)
        if re.search(r'\(Part\s+[IVXLCDM]+\..*?\)', stripped, re.IGNORECASE):
            continue
        # Remove raw page numbers at the very bottom
        if re.match(r'^\d+$', stripped):
            continue
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def parse_constitution(pdf_path: Path) -> list[Document]:
    """
    High-fidelity Constitution parser. Loads the Preamble and parses Articles 1-395 from pages 31 to 282.
    """
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    documents = []

    # 1. Load Preamble (typically Page 31 in 0-based index)
    preamble_text = ""
    try:
        if total_pages > 31:
            p31_text = reader.pages[31].extract_text() or ""
            if "PREAMBLE" in p31_text:
                preamble_text = p31_text.split("PREAMBLE")[-1].strip()
                preamble_text = re.split(r'\n\s*1\.\s+Subs\b', preamble_text)[0].strip()
    except Exception as e:
        print(f"Warning: Failed to extract Preamble: {e}")
        
    if preamble_text:
        documents.append(Document(
            page_content=f"Preamble\n\n{preamble_text}",
            metadata={
                "article": "Preamble",
                "source": "Constitution of India"
            }
        ))
        
    # 2. Extract and concatenate Articles text (Pages 32 to 282 inclusive)
    articles_full_text = ""
    for page_idx in range(32, 283):
        if page_idx >= total_pages:
            break
        page_text = reader.pages[page_idx].extract_text() or ""
        cleaned_page = clean_constitution_text(page_text)
        articles_full_text += "\n" + cleaned_page

    # Regex to find starting positions of articles
    article_pattern = re.compile(
        r'\n\s*(\d+[A-Z]?)\.\s+([A-Za-z0-9\s,⎯—–\-\(\)/\"”’‘\'“”]+)(?:\.—|\.\s*—|\.\s*–|\.\s*⎯)'
    )
    
    matches = list(article_pattern.finditer(articles_full_text))
    
    # Part scanning
    part_pattern = re.compile(r'\bPART\s+([IVXLCDM]+)\s*\n\s*([^\n]+)', re.IGNORECASE)
    parts_list = list(part_pattern.finditer(articles_full_text))
    
    def get_part_for_position(pos):
        current_part = ""
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
        
        content_text = f"Article {art_num}: {art_title}\n{art_part}\n\n{art_content}".strip()
        
        documents.append(Document(
            page_content=content_text,
            metadata={
                "article": f"Article {art_num}",
                "source": "Constitution of India"
            }
        ))
        
    return documents

def parse_criminal_code(pdf_path: Path) -> list[Document]:
    """
    Parses criminal law codes (BNS, BNSS, BSA) page-by-page and splits along Section boundaries.
    """
    import pypdf
    filename = pdf_path.name.lower()
    reader = pypdf.PdfReader(str(pdf_path))
    full_text = "\n".join([page.extract_text() or "" for page in reader.pages])
    documents = []

    # Determine source name based on file name
    if "bnss" in filename:
        source_name = "Bharatiya Nagarik Suraksha Sanhita (BNSS)"
    elif "bns" in filename:
        source_name = "Bharatiya Nyaya Sanhita (BNS)"
    elif "bsa" in filename:
        source_name = "Bharatiya Sakshya Adhiniyam (BSA)"
    else:
        source_name = pdf_path.stem

    # Split by section boundaries: newline followed by optional spaces, a section number, dot, optional space/non-breaking space, and an uppercase letter.
    section_pattern = r'\n(?=\s*\d+\.[\s\xa0]*[A-Z])'
    raw_chunks = re.split(section_pattern, full_text)
    
    for raw_chunk in raw_chunks:
        text = raw_chunk.strip()
        if not text:
            continue
            
        # Extract section number (e.g. "98.Whoever" or "105. Whoever")
        match = re.match(r'^\s*(\d+)\.', text)
        if not match:
            match = re.search(r'\b(\d+)\.', text)
        sec_num = match.group(1) if match else "General"
        
        doc = Document(
            page_content=text,
            metadata={
                "article": f"Section {sec_num}",
                "source": source_name
            }
        )
        documents.append(doc)

    return documents

def get_embedding_function():
    from langchain_community.embeddings import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

def get_vector_store():
    from langchain_community.vectorstores import Chroma
    embeddings = get_embedding_function()
    return Chroma(
        collection_name=settings.COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_PERSIST_DIR,
        collection_metadata={"hnsw:space": "cosine"}
    )

def ingest_documents(docs_dir: str = settings.DOCUMENTS_DIR) -> int:
    from langchain_community.vectorstores import Chroma
    dir_path = Path(docs_dir)
    pdf_files = list(dir_path.glob("*.pdf"))
    
    if not pdf_files:
        print("No PDF files found to ingest.")
        return 0

    # Clear existing Chroma persistent database directory to avoid duplicates
    db_dir = Path(settings.CHROMA_PERSIST_DIR)
    if db_dir.exists():
        print(f"Clearing existing Chroma database at {db_dir}...")
        try:
            shutil.rmtree(db_dir)
            print("Database cleared successfully.")
        except Exception as e:
            print(f"Warning: Could not clear database directory: {e}. Trying to overwrite.")

    all_docs = []
    for pdf in pdf_files:
        print(f"Parsing PDF: {pdf.name}...")
        filename = pdf.name.lower()
        if "constitution" in filename:
            docs = parse_constitution(pdf)
        else:
            docs = parse_criminal_code(pdf)
        all_docs.extend(docs)
        print(f"Extracted {len(docs)} segments from {pdf.name}.")

    if not all_docs:
        print("No valid documents extracted.")
        return 0

    print(f"Generating embeddings using {settings.EMBEDDING_MODEL} model and saving {len(all_docs)} segments into ChromaDB...")
    embeddings = get_embedding_function()
    Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        collection_name=settings.COLLECTION_NAME,
        persist_directory=settings.CHROMA_PERSIST_DIR,
        collection_metadata={"hnsw:space": "cosine"}
    )

    return len(all_docs)

if __name__ == "__main__":
    count = ingest_documents()
    print(f"Successfully ingested {count} distinct segments into ChromaDB.")