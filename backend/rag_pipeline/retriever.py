import os
import sys
import re
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from rag_pipeline.d1_client import D1Client

# Paths
CHROMA_DB_DIR = str(Path(__file__).resolve().parents[1] / "chroma_db")
ARTICLES_INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "articles_index.json"

# Cache embeddings model to avoid reloading on every import
_embeddings = None
_vector_store = None
_d1_client = None
_article_index = None

# Regex to match Articles and Sections (e.g. Article 21, BNS Section 15, Section 15 of BNSS)
ARTICLE_REFERENCE_PATTERN = re.compile(
    r'\b(?:(?:(BNS|BNSS|BSA)\s+(?:section|sec\.?)\s*(\d+[A-Z]?))|(?:(?:section|sec\.?)\s*(\d+[A-Z]?)\s+of\s+(BNS|BNSS|BSA))|(?:(?:article|art\.?)\s*(\d+[A-Z]?)))\b',
    re.IGNORECASE,
)

def extract_article_numbers(query: str) -> list[str]:
    """
    Returns explicitly mentioned Article or Section references in user order.
    Example: "Article 21" -> ["21"]
             "BNS Section 15" -> ["BNS Section 15"]
             "Section 9 of BSA" -> ["BSA Section 9"]
    """
    seen = set()
    article_numbers = []

    def add_number(raw_number: str) -> None:
        normalized = raw_number
        match = re.match(r'^(BNS|BNSS|BSA)\s+SECTION\s+(\d+[A-Z]?)$', raw_number.upper())
        if match:
            normalized = f"{match.group(1)} Section {match.group(2)}"
        else:
            normalized = raw_number.upper()
            
        if normalized not in seen:
            seen.add(normalized)
            article_numbers.append(normalized)

    standalone_number = re.fullmatch(r'\s*(\d{1,3}[A-Z]?)\s*', query)
    if standalone_number:
        return [standalone_number.group(1).upper()]

    for match in ARTICLE_REFERENCE_PATTERN.finditer(query):
        g1, g2, g3, g4, g5 = match.groups()
        if g1 and g2:
            val = f"{g1.upper()} Section {g2.upper()}"
        elif g3 and g4:
            val = f"{g4.upper()} Section {g3.upper()}"
        elif g5:
            val = g5.upper()
        else:
            continue
        add_number(val)

    return article_numbers

def _format_article_row(row, score: float = 1.0) -> dict:
    return {
        "content": row["content"],
        "metadata": {
            "number": str(row["number"]),
            "title": row["title"],
            "part": row["part"],
            "type": row["type"]
        },
        "score": score
    }

def _article_sort_key(number: str) -> tuple[int, str]:
    match = re.match(r"(\d+)([A-Z]*)", str(number))
    if not match:
        return (9999, str(number))
    return (int(match.group(1)), match.group(2))

def _load_article_index() -> list[dict]:
    global _article_index
    if _article_index is not None:
        return _article_index
    if not ARTICLES_INDEX_PATH.exists():
        _article_index = []
        return _article_index
    try:
        with ARTICLES_INDEX_PATH.open("r", encoding="utf-8") as handle:
            raw_rows = json.load(handle)
        _article_index = [
            {
                "number": str(row.get("number", "")).strip(),
                "title": str(row.get("title", "")).strip(),
                "part": str(row.get("part", "")).strip(),
                "content": str(row.get("content", "")).strip(),
                "type": str(row.get("type", "article")).strip() or "article",
            }
            for row in raw_rows
            if row.get("number") and row.get("content")
        ]
    except Exception as exc:
        print(f"Warning: Could not load article index: {exc}")
        _article_index = []
    return _article_index

def _format_index_row(row: dict, score: float = 1.0) -> dict:
    return {
        "content": row["content"],
        "metadata": {
            "number": str(row["number"]),
            "title": row["title"],
            "part": row["part"],
            "type": row["type"],
        },
        "score": score,
    }

def _exact_article_docs_from_index(article_numbers: list[str]) -> list[dict]:
    indexed_articles = {
        str(row["number"]).upper(): row
        for row in _load_article_index()
    }
    return [
        _format_index_row(indexed_articles[number.upper()], score=1.0)
        for number in article_numbers
        if number.upper() in indexed_articles
    ]

def _keyword_list(query: str) -> list[str]:
    stop_words = {
        "about", "article", "articles", "explain", "match", "matching", "please",
        "show", "tell", "what", "which", "with", "from", "give", "simple", "right",
    }
    keywords: list[str] = []
    seen = set()
    for raw_word in re.split(r'\W+', query.lower()):
        word = raw_word.strip()
        if len(word) <= 3 or word in stop_words or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
    return keywords[:8]

def _keyword_search_d1(d1: D1Client, query: str, k: int) -> list[dict]:
    """
    Fast Render/local fallback that avoids loading sentence-transformers when D1
    can answer a topic search directly.
    """
    if not d1.is_configured():
        return []

    keywords = _keyword_list(query)
    if not keywords:
        return []

    score_parts = []
    score_params = []
    where_parts = []
    where_params = []
    for keyword in keywords:
        like = f"%{keyword}%"
        score_parts.append(
            "(CASE WHEN LOWER(title) LIKE LOWER(?) THEN 3 ELSE 0 END + "
            "CASE WHEN LOWER(part) LIKE LOWER(?) THEN 2 ELSE 0 END + "
            "CASE WHEN LOWER(content) LIKE LOWER(?) THEN 1 ELSE 0 END)"
        )
        score_params.extend([like, like, like])
        where_parts.append("(LOWER(title) LIKE LOWER(?) OR LOWER(part) LIKE LOWER(?) OR LOWER(content) LIKE LOWER(?))")
        where_params.extend([like, like, like])

    sql = (
        "SELECT number, title, part, content, type, "
        f"({' + '.join(score_parts)}) AS match_score "
        "FROM articles "
        "WHERE "
        f"({' OR '.join(where_parts)}) "
        "ORDER BY match_score DESC, CAST(number AS INTEGER) ASC "
        "LIMIT ?"
    )

    rows = d1.execute(sql, score_params + where_params + [k])
    max_score = max(len(keywords) * 6, 1)
    results = []
    for row in rows:
        score = min(float(row.get("match_score", 1)) / max_score, 1.0)
        results.append(_format_article_row(row, score=score))
    return results

def _keyword_search_index(query: str, k: int) -> list[dict]:
    keywords = _keyword_list(query)
    if not keywords:
        return []

    scored_rows = []
    max_score = max(len(keywords) * 6, 1)
    for row in _load_article_index():
        title = row.get("title", "").lower()
        part = row.get("part", "").lower()
        content = row.get("content", "").lower()
        score = 0
        for keyword in keywords:
            if keyword in title:
                score += 3
            if keyword in part:
                score += 2
            if keyword in content:
                score += 1
        if score:
            scored_rows.append((score, row))

    scored_rows.sort(key=lambda item: (-item[0], _article_sort_key(item[1].get("number", ""))))
    return [
        _format_index_row(row, score=min(score / max_score, 1.0))
        for score, row in scored_rows[:k]
    ]

def get_d1_client():
    global _d1_client
    if _d1_client is None:
        _d1_client = D1Client()
    return _d1_client

def get_vector_store():
    """
    Lazy initialization of embeddings and Chroma vector store.
    """
    global _embeddings, _vector_store
    if _vector_store is None:
        # Import heavy packages lazily (prevents crashing on Cloudflare Workers edge environment)
        from langchain_chroma import Chroma
        from langchain_community.embeddings import HuggingFaceEmbeddings

        if _embeddings is None:
            # Load the sentence-transformers model (fast, runs locally)
            _embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Initialize persistent ChromaDB
        if not os.path.exists(CHROMA_DB_DIR):
            raise FileNotFoundError(f"Chroma DB directory not found at: {CHROMA_DB_DIR}. Have you run data ingestion first?")
            
        _vector_store = Chroma(
            persist_directory=CHROMA_DB_DIR,
            embedding_function=_embeddings
        )
    return _vector_store

async def retrieve(query: str, k: int = 4, d1_binding=None):
    """
    Embeds the user query and retrieves top k matching chunks.
    If running inside Cloudflare Workers (d1_binding provided), queries D1 natively using SQL.
    Otherwise, uses the local Chroma DB + D1 REST API client fallback.
    """
    article_numbers = extract_article_numbers(query)

    # ----------------------------------------------------
    # Case A: Running inside Cloudflare Worker (d1_binding active)
    # ----------------------------------------------------
    if d1_binding is not None:
        print("Using native Cloudflare D1 worker binding for retrieval.")

        if article_numbers:
            exact_article_docs = []
            try:
                for target_number in article_numbers:
                    sql = "SELECT number, title, part, content, type FROM articles WHERE number = ? AND type = 'article' LIMIT 1"
                    resp = await d1_binding.prepare(sql).bind(str(target_number)).all()
                    rows = resp.results
                    if hasattr(rows, "to_py"):
                        rows = rows.to_py()
                    if rows:
                        exact_article_docs.append(_format_article_row(rows[0]))
            except Exception as e:
                print(f"Worker D1 exact match query failed: {e}")
            return exact_article_docs

        # 2. Keyword fallback query (Edge-compatible keyword search)
        formatted_results = []

        try:
            keywords = _keyword_list(query)
            if keywords:
                conditions = []
                sql_params = []
                for kw in keywords:
                    conditions.append("(content LIKE ? OR title LIKE ?)")
                    sql_params.extend([f"%{kw}%", f"%{kw}%"])
                
                sql = f"SELECT number, title, part, content, type FROM articles WHERE ({' OR '.join(conditions)}) LIMIT ?"
                sql_params.append(k)

                resp = await d1_binding.prepare(sql).bind(*sql_params).all()
                rows = resp.results
                if hasattr(rows, "to_py"):
                    rows = rows.to_py()

                for row in rows:
                    formatted_results.append({
                        "content": row["content"],
                        "metadata": {
                            "number": row["number"],
                            "title": row["title"],
                            "part": row["part"],
                            "type": row["type"]
                        },
                        "score": 0.8 # Constant confidence score for keyword matches
                    })
        except Exception as e:
            print(f"Worker D1 keyword similarity search failed: {e}")

        return formatted_results[:k]

    # ----------------------------------------------------
    # Case B: Local Development / Render (HTTP REST D1 API)
    # ----------------------------------------------------
    d1 = get_d1_client()
    
    # 1. Exact Article requests must return only the requested Article(s).
    if article_numbers:
        exact_article_docs = []
        print(f"Detected exact article query for: {', '.join('Article ' + n for n in article_numbers)}")

        indexed_docs = _exact_article_docs_from_index(article_numbers)
        exact_article_docs.extend(indexed_docs)
        found_numbers = {str(doc["metadata"].get("number")) for doc in exact_article_docs}
        missing_numbers = [target_number for target_number in article_numbers if target_number not in found_numbers]

        try:
            if missing_numbers and d1.is_configured():
                for target_number in missing_numbers:
                    sql = "SELECT number, title, part, content, type FROM articles WHERE number = ? AND type = 'article' LIMIT 1"
                    rows = d1.execute(sql, [str(target_number)])
                    if rows:
                        exact_article_docs.append(_format_article_row(rows[0]))
                        print(f"D1 exact match found for Article {target_number}!")
        except Exception as e:
            print(f"Warning: D1 exact match query failed: {e}")

        found_numbers = {str(doc["metadata"].get("number")) for doc in exact_article_docs}
        missing_numbers = [target_number for target_number in article_numbers if target_number not in found_numbers]
        if missing_numbers:
            if os.getenv("ENABLE_CHROMA_FALLBACK", "").strip().lower() not in {"1", "true", "yes"}:
                return exact_article_docs
            try:
                db = get_vector_store()
                for target_number in missing_numbers:
                    exact_docs = db.get(
                        where={"number": {"$eq": str(target_number)}}
                    )
                    if exact_docs and exact_docs.get("documents"):
                        doc_content = exact_docs["documents"][0]
                        doc_meta = exact_docs["metadatas"][0]
                        exact_article_docs.append({
                            "content": doc_content,
                            "metadata": doc_meta,
                            "score": 1.0
                        })
                        print(f"Chroma exact match found for Article {target_number}!")
            except Exception as e:
                print(f"Warning: Chroma exact match query failed: {e}")

        return exact_article_docs
            
    # 2. Prefer the committed lightweight index on Render/local deployments.
    indexed_keyword_results = _keyword_search_index(query, k)
    if indexed_keyword_results:
        return indexed_keyword_results[:k]

    # 3. D1 keyword fallback for deployments that intentionally keep the index empty.
    try:
        d1_keyword_results = _keyword_search_d1(d1, query, k)
        if d1_keyword_results:
            return d1_keyword_results[:k]
    except Exception as e:
        print(f"Warning: D1 keyword search failed: {e}. Falling back to Chroma.")

    if os.getenv("ENABLE_CHROMA_FALLBACK", "").strip().lower() not in {"1", "true", "yes"}:
        return []

    # 4. Similarity search using Chroma
    db = get_vector_store()
    try:
        results = db.similarity_search_with_relevance_scores(query, k=k)
    except Exception as e:
        print(f"Error during similarity search: {e}")
        docs = db.similarity_search(query, k=k)
        results = [(doc, 1.0) for doc in docs]
        
    formatted_results = []
    
    seen_docs = set()

    for doc, score in results:
        doc_num = doc.metadata.get("number")
        doc_type = doc.metadata.get("type")

        doc_key = (str(doc_num), str(doc_type))
        if doc_key in seen_docs:
            continue
        seen_docs.add(doc_key)
            
        # Fetch from D1 if configured, fallback to Chroma document content
        content = doc.page_content
        metadata = doc.metadata
        
        if d1.is_configured():
            try:
                # Query D1 for this specific document number and type
                sql = "SELECT number, title, part, content, type FROM articles WHERE number = ? AND type = ? LIMIT 1"
                rows = d1.execute(sql, [str(doc_num), str(doc_type)])
                if rows:
                    row = rows[0]
                    content = row["content"]
                    metadata = {
                        "number": row["number"],
                        "title": row["title"],
                        "part": row["part"],
                        "type": row["type"]
                    }
            except Exception as e:
                print(f"Warning: Failed to fetch document {doc_num} from D1: {e}. Falling back to Chroma.")
                
        formatted_results.append({
            "content": content,
            "metadata": metadata,
            "score": float(score)
        })
        
    return formatted_results[:k]

if __name__ == "__main__":
    # Test retrieval
    test_query = "What is the right to equality?"
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
        
    print(f"Retrieving for query: '{test_query}'...")
    try:
        docs = asyncio.run(retrieve(test_query, k=3))
        for i, doc in enumerate(docs):
            print(f"\nResult #{i+1} (Score: {doc['score']:.4f}):")
            print(f"Type: {doc['metadata'].get('type')}, Number: {doc['metadata'].get('number')}")
            print(f"Title: {doc['metadata'].get('title')}")
            print(f"Text Snippet:\n{doc['content'][:200]}...")
    except Exception as e:
        print(f"Error testing retrieval: {e}")
        print("Please ensure you run ingest.py first to create the database.")
