from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import shutil
from pathlib import Path

from config import settings
from ingester import ingest_documents
from rag_engine import RAGEngine

app = FastAPI(title="RAG AI Assistant API", version="1.0.0")

# Lazy initialization of RAG engine
rag_engine = None

@app.on_event("startup")
def startup_event():
    global rag_engine
    rag_engine = RAGEngine()

class QueryRequest(BaseModel):
    question: str
    email: str = None

class ArticleDetail(BaseModel):
    number: str
    title: str
    part: str
    content: str

class AskResponse(BaseModel):
    answer: str
    articles_cited: list[str]
    retrieved_articles: list[ArticleDetail] = []

@app.get("/")
def health_check():
    return {"status": "ok", "message": "RAG Assistant API is running"}

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a .pdf or .txt file directly to the data folder."""
    data_dir = Path(settings.DOCUMENTS_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = data_dir / file.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Auto-trigger ingestion
    chunks_count = ingest_documents()
    
    return {
        "filename": file.filename,
        "status": "uploaded & ingested",
        "total_chunks_indexed": chunks_count
    }

@app.post("/ask", response_model=AskResponse)
def ask_question(request: QueryRequest):
    """Query the RAG system with a question."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    
    try:
        response = rag_engine.query(request.question)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)