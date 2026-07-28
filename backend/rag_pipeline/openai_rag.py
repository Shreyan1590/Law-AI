import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# Define paths
CHROMA_DB_DIR = str(Path(__file__).resolve().parents[1] / "chroma_db_openai")

# Lazy loaders for OpenAI and Chroma objects
_client = None
_vector_store = None

def get_openai_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in backend/.env file.")
        _client = OpenAI(api_key=api_key)
    return _client

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in backend/.env file.")
            
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=api_key
        )

        if not os.path.exists(CHROMA_DB_DIR):
            raise FileNotFoundError(f"Chroma DB directory not found at: {CHROMA_DB_DIR}. Have you run data_ingestion/ingest_openai.py first?")

        _vector_store = Chroma(
            persist_directory=CHROMA_DB_DIR,
            embedding_function=embeddings
        )
    return _vector_store

def retrieve_chunks(query: str, k: int = 5):
    """
    Retrieves the top-k chunks from the Chroma vector database using similarity search.
    """
    db = get_vector_store()
    try:
        # Perform similarity search
        docs = db.similarity_search(query, k=k)
        return docs
    except Exception as e:
        print(f"Error during similarity search: {e}", file=sys.stderr)
        return []

def generate_grounded_answer(query: str, chunks: list) -> str:
    """
    Constructs a context-aware prompt using retrieved chunks and calls the OpenAI ChatCompletion API.
    Enforces strict grounding requirements: "The answer is not available in the provided document."
    """
    if not chunks:
        return "The answer is not available in the provided document."

    # Construct the context string
    context_parts = []
    for i, doc in enumerate(chunks):
        page_num = doc.metadata.get("page", "Unknown")
        context_parts.append(f"--- Chunk {i+1} (PDF Page: {page_num}) ---\n{doc.page_content}")
    
    context_str = "\n\n".join(context_parts)

    # Setup messages for OpenAI ChatCompletion
    system_instruction = (
        "You are a Retrieval-Augmented Generation assistant. Your role is to answer user questions strictly based on the content of the provided context.\n"
        "You must not hallucinate or invent information outside the context. If the answer is not found or cannot be reasonably inferred from the provided context, clearly state: \"The answer is not available in the provided document.\"\n"
        "Do not invent any details or answer from external knowledge."
    )

    user_prompt = (
        f"Context from PDF:\n"
        f"\"\"\"\n"
        f"{context_str}\n"
        f"\"\"\"\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )

    client = get_openai_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0, # Make response as deterministic and grounded as possible
            max_tokens=800
        )
        answer = response.choices[0].message.content.strip()
        return answer
    except Exception as e:
        print(f"Error calling OpenAI ChatCompletion: {e}", file=sys.stderr)
        return "Error: Failed to generate response from OpenAI API."

def run_rag_pipeline(query: str, k: int = 5) -> dict:
    """
    Main entry point for executing the OpenAI RAG flow:
    1. Similarity search to retrieve relevant chunks.
    2. Generation using OpenAI ChatCompletion.
    """
    chunks = retrieve_chunks(query, k=k)
    answer = generate_grounded_answer(query, chunks)
    
    # Structure citations for compatibility with the existing frontend
    retrieved_articles = []
    articles_cited = set()

    for doc in chunks:
        # Extract page number or metadata if present
        page = doc.metadata.get("page", "")
        # For cited list, we can represent it as "Page X"
        source_label = f"Page {page + 1}" if isinstance(page, int) else "Page Unknown"
        articles_cited.add(source_label)

        # Parse basic article info if the text snippet mentions "Article X"
        import re
        match = re.search(r'\bArticle\s+(\d+[A-Z]?)\b', doc.page_content, re.IGNORECASE)
        number = match.group(1) if match else (f"Page {page + 1}" if isinstance(page, int) else "Chunk")
        
        retrieved_articles.append({
            "number": str(number),
            "title": f"Excerpt from {source_label}",
            "part": "Constitution of India",
            "content": doc.page_content
        })

    return {
        "answer": answer,
        "articles_cited": sorted(list(articles_cited)),
        "retrieved_articles": retrieved_articles
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python openai_rag.py \"your query here\"")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    print(f"Querying OpenAI RAG: '{query}'...")
    
    try:
        result = run_rag_pipeline(query)
        print("\n--- Answer ---")
        print(result["answer"])
        print("\n--- Sources Cited ---")
        print(result["articles_cited"])
    except Exception as e:
        print(f"Error: {e}")
