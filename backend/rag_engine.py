from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from ingester import get_vector_store
from config import settings

SYSTEM_PROMPT = """You are Arasamaippu AI, a specialized legal Assistant on the Constitution of India and Indian Criminal Laws (Bharatiya Nyaya Sanhita - BNS, Bharatiya Nagarik Suraksha Sanhita - BNSS, and Bharatiya Sakshya Adhiniyam - BSA).

CRITICAL INSTRUCTIONS:
1. Answer the question based ONLY on the provided Context below.
2. If the user asks about specific criminal offenses or procedures, look for sections from BNS, BNSS, or BSA in the Context. If the user asks about constitutional provisions, look for Articles from the Constitution of India.
3. Do not make up information or use external knowledge outside the provided Context. If the answer cannot be found in the Context, state clearly: "I don't have enough information in my knowledge base to answer that."
4. Be precise, cite the specific Section or Article numbers from the Context, and explain the legal rule clearly.

Context:
{context}

Question:
{question}
"""

class RAGEngine:
    def __init__(self):
        import os
        self.vector_store = get_vector_store()
        
        google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        openai_api_key = settings.OPENAI_API_KEY.strip()
        
        # Check which LLM API key is available
        if openai_api_key and not openai_api_key.startswith("your_") and "sk-" in openai_api_key:
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                openai_api_key=openai_api_key,
                temperature=0.0
            )
            print("RAG LLM: Using OpenAI Chat API (gpt-4o-mini)")
        elif google_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
            self.llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=google_api_key,
                temperature=0.0
            )
            print(f"RAG LLM: Using Google Gemini API ({model_name})")
        else:
            self.llm = ChatOpenAI(
                model=settings.OLLAMA_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                api_key="ollama",
                temperature=0.0
            )
            print(f"RAG LLM: Using local Ollama ({settings.OLLAMA_MODEL})")
        self.prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)

    def query(self, question: str) -> dict:
        # 1. Retrieve the top-k most similar chunks from Chroma
        relevant_docs = self.vector_store.similarity_search(
            question, k=settings.RETRIEVAL_K
        )

        # 2. Build context string
        if relevant_docs:
            context_str = "\n\n".join([
                f"[{doc.metadata.get('article', 'Article/Section')} from {doc.metadata.get('source', 'Unknown')}]: {doc.page_content}"
                for doc in relevant_docs
            ])
        else:
            context_str = "No directly relevant Constitutional Articles or Criminal Penal Code sections found in the database for this query."

        # 3. Generate Answer
        chain = self.prompt | self.llm | StrOutputParser()
        answer = chain.invoke({
            "context": context_str,
            "question": question
        })

        retrieved_articles = []
        articles_cited = []
        for doc in relevant_docs:
            source = doc.metadata.get('source', 'Unknown')
            article = doc.metadata.get('article', '')
            articles_cited.append(f"{source}: {article}")
            
            content = doc.page_content
            number = article
            title = source
            part = ""
            
            if source == "Constitution of India" and content.startswith("Article "):
                try:
                    lines = content.split("\n")
                    first_line = lines[0]
                    if ":" in first_line:
                        parts = first_line.split(":", 1)
                        number = parts[0].strip()
                        title = parts[1].strip()
                    
                    if len(lines) > 1 and lines[1].startswith("Part "):
                        part = lines[1].strip()
                        content_body = "\n".join(lines[2:]).strip()
                    else:
                        content_body = "\n".join(lines[1:]).strip()
                except Exception:
                    content_body = content
            else:
                content_body = content
            retrieved_articles.append({
                "number": number,
                "title": title,
                "part": part,
                "content": content_body
            })

        return {
            "answer": answer,
            "articles_cited": list(dict.fromkeys(articles_cited)),
            "retrieved_articles": retrieved_articles
        }