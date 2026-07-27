import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv()

GREETINGS_PATTERN = re.compile(r'^\s*(hi+|hello+|hey+|hola|greetings|who are you|what is your name|what\'?s your name|who made you|who created you|what can you do)\b', re.IGNORECASE)
CRIMINAL_LAW_PATTERN = re.compile(r'\b(murder|strangulation|asphyxiation|theft|robbery|rape|dacoity|assault|ipc|bns|indian penal code|bharatiya nyaya sanhita|fir|police|bail|cheating|extortion)\b', re.IGNORECASE)

def generate_answer(question: str, retrieved_docs: list):
    """
    Directly formats the retrieved documents into a grounded, intent-aware legal response
    using markdown without calling any external LLM APIs, satisfying local RAG execution.
    """
    q_clean = question.strip().lower()

    # 1. Handle Greetings & Bot Identity Queries
    if GREETINGS_PATTERN.search(q_clean) or len(q_clean) <= 2:
        return {
            "answer": "Hello! I am **Arasamaippu AI**, your intelligent assistant for the **Constitution of India**.\n\n"
                      "How can I help you find constitutional provisions or fundamental rights today?\n\n"
                      "**Examples you can ask:**\n"
                      "• *'What is Article 21?'*\n"
                      "• *'What are my fundamental rights?'*\n"
                      "• *'What is the procedure for amending the Constitution?'*\n\n"
                      "**Disclaimer: This is general information, not legal advice. Consult a qualified lawyer for advice on your specific situation.**",
            "articles_cited": [],
            "retrieved_articles": []
        }

    # 2. Detect Criminal Offenses vs Constitutional Law Intent
    is_criminal_query = bool(CRIMINAL_LAW_PATTERN.search(q_clean))

    # Filter retrieved docs by score/relevance (if score available)
    filtered_docs = []
    for doc in retrieved_docs:
        score = doc.get("score", 1.0) if isinstance(doc, dict) else 1.0
        meta = doc.metadata if hasattr(doc, "metadata") else doc.get("metadata", {})
        # Always retain exact article matches or score >= 0.15
        if score >= 0.15 or meta.get("number"):
            filtered_docs.append(doc)

    if not filtered_docs:
        return {
            "answer": "No relevant articles from the Constitution of India were found matching your query.\n\n"
                      "Note: The Constitution of India establishes fundamental rights, state powers, and constitutional principles. Specific statutory laws (such as criminal offenses under IPC/BNS, contracts, or traffic regulations) are enacted under separate legislative statutes.\n\n"
                      "**Disclaimer: This is general information, not legal advice. Consult a qualified lawyer for advice on your specific situation.**",
            "articles_cited": [],
            "retrieved_articles": []
        }

    answer_parts = []
    
    if is_criminal_query:
        answer_parts.append(
            "### Legal Clarification on Criminal Offenses & Constitutional Scope:\n"
            "Specific criminal offenses (such as murder by strangulation/asphyxiation, theft, or assault) are defined and penalized under statutory criminal legislation—primarily the **Indian Penal Code (IPC)** (e.g., Section 300 & 302 for murder) and the **Bharatiya Nyaya Sanhita (BNS)** (e.g., Section 101 & 103 for murder)—rather than individual Constitutional Articles.\n\n"
            "However, from a **Constitutional Law** perspective, the **Constitution of India** guarantees fundamental rights protecting life and personal liberty, and establishes the judicial framework for criminal procedure:\n"
        )
    else:
        answer_parts.append("### Based on the retrieved provisions of the Constitution of India, here are the relevant articles matching your query:\n")

    articles_cited = []
    retrieved_articles_list = []

    for doc in filtered_docs:
        if hasattr(doc, "metadata"):
            meta = doc.metadata
            content = doc.page_content
        else:
            meta = doc.get("metadata", {})
            content = doc.get("content", "")

        doc_type = meta.get("type", "article").capitalize()
        doc_num = meta.get("number", "")
        doc_title = meta.get("title", "")
        doc_part = meta.get("part", "")

        if doc_num:
            articles_cited.append(f"Article {doc_num}")

        header = f"#### {doc_type} {doc_num}: {doc_title}"
        part_str = f"*{doc_part}*" if doc_part else ""

        body_content = content
        if body_content.startswith(f"Article {doc_num}: {doc_title}"):
            body_content = body_content.replace(f"Article {doc_num}: {doc_title}", "").strip()
            if body_content.startswith(f"Part: {doc_part}"):
                body_content = body_content.replace(f"Part: {doc_part}", "").strip()
            elif body_content.startswith(f"{doc_part}"):
                body_content = body_content.replace(f"{doc_part}", "").strip()

        if part_str:
            answer_parts.append(f"{header}\n{part_str}\n\n{body_content.strip()}\n")
        else:
            answer_parts.append(f"{header}\n\n{body_content.strip()}\n")

        retrieved_articles_list.append({
            "number": str(doc_num),
            "title": str(doc_title),
            "part": str(doc_part),
            "content": body_content.strip()
        })

    answer_text = "\n".join(answer_parts)
    answer_text += "\n**Disclaimer: This is general information, not legal advice. Consult a qualified lawyer for advice on your specific situation.**"

    unique_citations = sorted(list(set(articles_cited)), key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 999)

    return {
        "answer": answer_text,
        "articles_cited": unique_citations,
        "retrieved_articles": retrieved_articles_list
    }
