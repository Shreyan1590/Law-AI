from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from ingester import get_vector_store
from config import settings

SYSTEM_PROMPT = """You are a helpful AI Assistant. Answer the question based ONLY on the provided context below.
If the answer cannot be determined from the context, state clearly: "I don't have enough information in my knowledge base to answer that."

Context:
{context}

Question:
{question}
"""

def format_docs(docs):
    """Formats retrieved context documents into a unified context string."""
    return "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('source', 'Unknown')}]\n{doc.page_content}"
        for doc in docs
    )

class RAGEngine:
    def __init__(self):
        self.vector_store = get_vector_store()
        self.retriever = self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": settings.RETRIEVAL_K}
        )
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2,
            openai_api_key=settings.OPENAI_API_KEY
        )
        self.prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)

    def query(self, question: str) -> dict:
        """Executes retrieval and generation, returning the answer and sources."""
        # 1. Fetch relevant chunks
        retrieved_docs = self.retriever.invoke(question)
        
        # 2. Build and run chain
        chain = (
            {"context": lambda docs: format_docs(docs), "question": RunnablePassthrough()}
            | self.prompt
            | self.llm
            | StrOutputParser()
        )
        
        answer = chain.invoke(retrieved_docs, {"question": question})
        
        # 3. Extract unique source metadata
        sources = list(set(
            doc.metadata.get("source", "Unknown") for doc in retrieved_docs
        ))

        return {
            "answer": answer,
            "sources": sources,
            "chunks_retrieved": len(retrieved_docs)
        }