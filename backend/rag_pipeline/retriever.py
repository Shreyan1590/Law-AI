import os
import sys
import re
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from rag_pipeline.d1_client import D1Client

# Paths
CHROMA_DB_DIR = str(Path(__file__).resolve().parents[1] / "chroma_db")

# Cache embeddings model to avoid reloading on every import
_embeddings = None
_vector_store = None
_d1_client = None

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
    exact_article_doc = None
    match = re.search(r'\b(?:article|art\.?|section)\s*(\d+[A-Z]?)\b', query, re.IGNORECASE)

    # ----------------------------------------------------
    # Case A: Running inside Cloudflare Worker (d1_binding active)
    # ----------------------------------------------------
    if d1_binding is not None:
        print("Using native Cloudflare D1 worker binding for retrieval.")
        # 1. Exact match query
        if match:
            target_number = match.group(1)
            try:
                sql = "SELECT number, title, part, content, type FROM articles WHERE number = ? AND type = 'article' LIMIT 1"
                resp = await d1_binding.prepare(sql).bind(str(target_number)).all()
                rows = resp.results
                if hasattr(rows, "to_py"):
                    rows = rows.to_py()
                if rows:
                    row = rows[0]
                    exact_article_doc = {
                        "content": row["content"],
                        "metadata": {
                            "number": row["number"],
                            "title": row["title"],
                            "part": row["part"],
                            "type": row["type"]
                        },
                        "score": 1.0
                    }
            except Exception as e:
                print(f"Worker D1 exact match query failed: {e}")

        # 2. Keyword fallback query (Edge-compatible keyword search)
        formatted_results = []
        if exact_article_doc:
            formatted_results.append(exact_article_doc)

        try:
            keywords = [w.strip() for w in re.split(r'\W+', query) if len(w.strip()) > 3]
            if keywords:
                conditions = []
                sql_params = []
                for kw in keywords:
                    conditions.append("(content LIKE ? OR title LIKE ?)")
                    sql_params.extend([f"%{kw}%", f"%{kw}%"])
                
                sql = f"SELECT number, title, part, content, type FROM articles WHERE type = 'article' AND ({' OR '.join(conditions)}) LIMIT ?"
                sql_params.append(k)

                resp = await d1_binding.prepare(sql).bind(*sql_params).all()
                rows = resp.results
                if hasattr(rows, "to_py"):
                    rows = rows.to_py()

                for row in rows:
                    doc_num = row["number"]
                    # Skip duplication of exact match
                    if exact_article_doc and doc_num == exact_article_doc["metadata"]["number"]:
                        continue
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
    db = get_vector_store()
    d1 = get_d1_client()
    
    # 1. Try D1 exact match first if configured
    if match and d1.is_configured():
        target_number = match.group(1)
        print(f"Detected exact article query for: 'Article {target_number}'")
        try:
            sql = "SELECT number, title, part, content, type FROM articles WHERE number = ? AND type = 'article' LIMIT 1"
            rows = d1.execute(sql, [str(target_number)])
            if rows:
                row = rows[0]
                exact_article_doc = {
                    "content": row["content"],
                    "metadata": {
                        "number": row["number"],
                        "title": row["title"],
                        "part": row["part"],
                        "type": row["type"]
                    },
                    "score": 1.0
                }
                print(f"D1 Exact match found for Article {target_number}!")
        except Exception as e:
            print(f"Warning: D1 exact match query failed: {e}")
            
    # Fallback to Chroma exact match if D1 is not configured or failed
    if match and not exact_article_doc:
        target_number = match.group(1)
        try:
            exact_docs = db.get(
                where={
                    "$and": [
                        {"number": {"$eq": str(target_number)}},
                        {"type": {"$eq": "article"}}
                    ]
                }
            )
            if exact_docs and exact_docs.get("documents"):
                doc_content = exact_docs["documents"][0]
                doc_meta = exact_docs["metadatas"][0]
                exact_article_doc = {
                    "content": doc_content,
                    "metadata": doc_meta,
                    "score": 1.0
                }
                print(f"Chroma Exact match found for Article {target_number}!")
        except Exception as e:
            print(f"Warning: Chroma exact match query failed: {e}")
            
    # 2. Similarity search using Chroma
    try:
        results = db.similarity_search_with_relevance_scores(query, k=k)
    except Exception as e:
        print(f"Error during similarity search: {e}")
        docs = db.similarity_search(query, k=k)
        results = [(doc, 1.0) for doc in docs]
        
    formatted_results = []
    
    if exact_article_doc:
        formatted_results.append(exact_article_doc)
        
    for doc, score in results:
        doc_num = doc.metadata.get("number")
        doc_type = doc.metadata.get("type")
        
        # Avoid duplicating exact match
        if exact_article_doc and doc_num == exact_article_doc["metadata"].get("number") and doc_type == exact_article_doc["metadata"].get("type"):
            continue
            
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
