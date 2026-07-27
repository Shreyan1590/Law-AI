import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

ARTICLE_REFERENCE_PATTERN = re.compile(
    r"\b(?:article\s+number|article\s+no\.?|article|articles|art\.?|arts\.?)\s*(\d+[A-Z]?)\b",
    re.IGNORECASE,
)

GREETING_PATTERN = re.compile(
    r"^\s*(hi+|hello+|hey+|vanakkam|namaste|good\s+(morning|afternoon|evening)|who are you|what is your name|what'?s your name|what can you do)\b",
    re.IGNORECASE,
)

THANKS_OR_COMPLIMENT_PATTERN = re.compile(
    r"\b(thanks|thank you|great|good job|nice|excellent|awesome|super|helpful|well done|you are good|you'?re good|love you|appreciate)\b",
    re.IGNORECASE,
)

GENERAL_CHAT_PATTERN = re.compile(
    r"\b(how are you|tell me a joke|motivate me|compliment me|say something nice|good night|goodbye|bye)\b",
    re.IGNORECASE,
)

CONSTITUTIONAL_INTENT_PATTERN = re.compile(
    r"\b("
    r"constitution|constitutional|article|fundamental right|fundamental rights|directive principle|dpsp|"
    r"preamble|schedule|amendment|parliament|lok sabha|rajya sabha|president|governor|"
    r"supreme court|high court|writ|equality|liberty|freedom|religion|education|citizenship|"
    r"emergency|union|state|federal|election|reservation|minority|tribe|caste|language|"
    r"right to|duties|fundamental duties|ordinance|impeachment|money bill|finance commission"
    r")\b",
    re.IGNORECASE,
)

LEGAL_BUT_NON_CONSTITUTION_PATTERN = re.compile(
    r"\b("
    r"murder|strangulation|asphyxiation|theft|robbery|rape|dacoity|assault|ipc|bns|"
    r"indian penal code|bharatiya nyaya sanhita|fir|police|bail|cheating|extortion|"
    r"contract|divorce|property|traffic fine|consumer complaint"
    r")\b",
    re.IGNORECASE,
)

QUESTION_WORD_PATTERN = re.compile(
    r"\b(what|why|how|explain|meaning|doubt|clarify|clear|can|does|is|are|scope|example)\b",
    re.IGNORECASE,
)


def extract_article_numbers(question: str) -> list[str]:
    seen = set()
    numbers: list[str] = []

    def add_number(raw_number: str) -> None:
        number = raw_number.upper()
        if number not in seen:
            seen.add(number)
            numbers.append(number)

    standalone_number = re.fullmatch(r"\s*(\d{1,3}[A-Z]?)\s*", question)
    if standalone_number:
        return [standalone_number.group(1).upper()]
    for match in ARTICLE_REFERENCE_PATTERN.finditer(question):
        add_number(match.group(1))

        tail = question[match.end() :]
        offset = 0
        while True:
            extra = re.match(r"\s*(?:,|and|&)\s*(\d{1,3}[A-Z]?)\b", tail[offset:], re.IGNORECASE)
            if not extra:
                break
            add_number(extra.group(1))
            offset += extra.end()

    return numbers


def should_answer_without_retrieval(question: str) -> bool:
    """
    Skips expensive / irrelevant retrieval for friendly/general questions.
    Constitutional or legal-looking questions still go through retrieval.
    """
    q = question.strip()
    if not q:
        return True
    if ARTICLE_REFERENCE_PATTERN.search(q) or CONSTITUTIONAL_INTENT_PATTERN.search(q):
        return False
    if LEGAL_BUT_NON_CONSTITUTION_PATTERN.search(q):
        return True
    # Anything that is not Constitution/legal intent is a general assistant question.
    # This prevents unrelated Constitution Articles from appearing for ordinary chat.
    if len(q.split()) >= 2:
        return True
    return bool(
        GREETING_PATTERN.search(q)
        or THANKS_OR_COMPLIMENT_PATTERN.search(q)
        or GENERAL_CHAT_PATTERN.search(q)
    )


def _has_constitutional_intent(question: str) -> bool:
    return bool(
        ARTICLE_REFERENCE_PATTERN.search(question)
        or CONSTITUTIONAL_INTENT_PATTERN.search(question)
    )


def _is_article_doubt(question: str) -> bool:
    return bool(ARTICLE_REFERENCE_PATTERN.search(question) and QUESTION_WORD_PATTERN.search(question))


def _doc_parts(doc: Any) -> tuple[dict, str, float]:
    if hasattr(doc, "metadata"):
        meta = doc.metadata or {}
        content = getattr(doc, "page_content", "") or ""
        score = getattr(doc, "score", 1.0)
    else:
        if isinstance(doc, dict):
            meta = doc.get("metadata") or {
                "number": doc.get("number", ""),
                "title": doc.get("title", ""),
                "part": doc.get("part", ""),
                "type": doc.get("type", "article"),
            }
            content = doc.get("content", "") or doc.get("page_content", "")
        else:
            meta = {}
            content = ""
        score = doc.get("score", 1.0) if isinstance(doc, dict) else 1.0
    return meta, content, float(score or 0.0)


def _clean_article_content(content: str, meta: dict) -> str:
    doc_num = str(meta.get("number", "")).strip()
    doc_title = str(meta.get("title", "")).strip()
    doc_part = str(meta.get("part", "")).strip()

    cleaned = (content or "").strip()
    header_patterns = [
        rf"^\s*Article\s+{re.escape(doc_num)}\s*:\s*{re.escape(doc_title)}\s*",
        rf"^\s*Article\s+{re.escape(doc_num)}\s*[.\-:]\s*{re.escape(doc_title)}\s*",
        rf"^\s*{re.escape(doc_num)}\.\s*{re.escape(doc_title)}[.\-]*\s*",
    ]
    for pattern in header_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    if doc_part:
        cleaned = re.sub(rf"^\s*Part:\s*{re.escape(doc_part)}\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(rf"^\s*{re.escape(doc_part)}\s*", "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned


def _normalise_docs(retrieved_docs: list) -> list[dict]:
    docs: list[dict] = []
    seen = set()
    for doc in retrieved_docs or []:
        meta, content, score = _doc_parts(doc)
        number = str(meta.get("number", "")).strip()
        doc_type = str(meta.get("type", "article")).strip().lower() or "article"
        if not number:
            continue
        key = (doc_type, number)
        if key in seen:
            continue
        seen.add(key)
        docs.append(
            {
                "number": number,
                "title": str(meta.get("title", "")).strip(),
                "part": str(meta.get("part", "")).strip(),
                "type": doc_type,
                "content": _clean_article_content(content, meta),
                "score": score,
            }
        )
    return docs


def _citation_sort_key(citation: str) -> tuple[int, str]:
    match = re.search(r"\d+", citation)
    return (int(match.group(0)) if match else 9999, citation)


def _article_citations(docs: list[dict]) -> list[str]:
    citations = []
    seen = set()
    for doc in docs:
        citation = f"Article {doc['number']}"
        if citation not in seen:
            seen.add(citation)
            citations.append(citation)
    return sorted(citations, key=_citation_sort_key)


def _retrieved_articles(docs: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "number": str(doc["number"]),
            "title": str(doc["title"]),
            "part": str(doc["part"]),
            "content": str(doc["content"]),
        }
        for doc in docs
    ]


def _safe_google_api_key() -> str:
    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key or api_key.lower().startswith("your_"):
        return ""
    return api_key


def _call_gemini(prompt: str, timeout: int = 8) -> str | None:
    """
    Optional LLM polish. The app remains functional without GOOGLE_API_KEY.
    """
    api_key = _safe_google_api_key()
    if not api_key:
        return None

    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 900,
        },
    }

    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
        return text.strip() or None
    except Exception as exc:
        print(f"Gemini answer polish skipped: {exc}")
        return None


def _fallback_general_answer(question: str) -> str:
    q = question.strip().lower()
    if GREETING_PATTERN.search(q):
        return (
            "Hi! I'm **Arasamaippu AI** - your friendly assistant for the Constitution of India.\n\n"
            "You can ask me things like:\n\n"
            "- \"What is Article 21?\"\n"
            "- \"Which Articles match right to equality?\"\n"
            "- \"Explain my doubt about Article 19.\"\n\n"
            "I'll keep it clear, simple, and grounded."
        )

    if THANKS_OR_COMPLIMENT_PATTERN.search(q):
        return (
            "Thank you - that genuinely made my day a little brighter.\n\n"
            "You're doing well too: asking precise questions is exactly how legal ideas become easier to understand."
        )

    if "how are you" in q:
        return (
            "I'm doing well - focused, caffeinated in spirit, and ready to help. "
            "Tell me what you want to understand, and I'll make it clear."
        )

    what_is_match = re.match(r"^\s*(what\s+is|what\s+are|explain|meaning\s+of)\s+(.+?)\??\s*$", question, re.IGNORECASE)
    if what_is_match:
        topic = what_is_match.group(2).strip()
        return (
            f"### {topic.capitalize()}\n\n"
            f"{topic.capitalize()} is a concept that can be understood by looking at its main idea, purpose, and real-life use.\n\n"
            "- **Main idea:** It refers to the basic meaning or principle behind the term.\n"
            "- **Why it matters:** It helps people understand how something works in society, law, technology, or daily life.\n"
            "- **Simple way to think about it:** Break it into smaller parts and ask: what does it do, who does it affect, and why is it important?\n\n"
            "If you want, ask me the same question with a little more context, and I'll explain it more precisely."
        )

    return (
        "Sure - I can help with general questions too. My strongest area is the **Constitution of India**, "
        "but I can also explain ordinary concepts in a friendly, simple way.\n\n"
        "Ask the question directly, and I'll answer clearly. If it needs current/live facts, please remember I may not have real-time updates."
    )


def _general_answer(question: str) -> dict:
    llm_answer = _call_gemini(
        "You are Arasamaippu AI, a warm and friendly assistant. "
        "Answer the user's general question clearly and conversationally. "
        "If the user asks a legal question, explain it as general information and add a short not-legal-advice disclaimer. "
        "If the question needs live/current information, say that you may not have live updates. "
        "Do not invent citations.\n\n"
        f"User question: {question}"
    )

    return {
        "answer": llm_answer or _fallback_general_answer(question),
        "articles_cited": [],
        "retrieved_articles": [],
    }


def _grounded_article_explanation(question: str, docs: list[dict], specific: bool) -> str | None:
    if not docs:
        return None
    context = "\n\n".join(
        f"Article {doc['number']}: {doc['title']}\nPart: {doc['part']}\nText:\n{doc['content']}"
        for doc in docs
    )
    prompt = (
        "You are Arasamaippu AI, a friendly assistant explaining the Constitution of India. "
        "Use ONLY the article text below. Do not cite Articles that are not in the provided context. "
        "If the user asks about a specific Article, explain only that Article. "
        "Use simple language, answer the user's doubt directly, and include a short disclaimer that this is not legal advice.\n\n"
        f"User question: {question}\n\n"
        f"Article context:\n{context}"
    )
    answer = _call_gemini(prompt)
    if not answer:
        return None
    if specific and len(docs) == 1 and f"Article {docs[0]['number']}" not in answer:
        answer = f"### Article {docs[0]['number']}: {docs[0]['title']}\n\n{answer}"
    return answer


def _specific_article_answer(question: str, docs: list[dict]) -> str:
    if len(docs) == 1:
        doc = docs[0]
        heading = f"### Article {doc['number']}: {doc['title']}"
        part = f"*{doc['part']}*\n\n" if doc["part"] else ""
        doubt_intro = (
            "**Direct explanation:** Based on this Article, here is the clear meaning of the provision you asked about.\n\n"
            if _is_article_doubt(question)
            else "**Simple meaning:** Here is the Article in a clear form.\n\n"
        )
        return (
            f"{heading}\n\n"
            f"{part}"
            f"{doubt_intro}"
            f"- This Article deals with **{doc['title'] or 'the constitutional rule stated below'}**.\n"
            "- Read the exact text carefully because the legal effect comes from these words.\n"
            "- If your doubt is about a real-life case, the facts and court interpretation can matter.\n\n"
            "**Exact constitutional text:**\n\n"
            f"{doc['content']}\n\n"
            "**Disclaimer:** This is general information, not legal advice. For a specific legal problem, please consult a qualified advocate."
        )

    parts = [
        "### Specific Articles requested",
        "",
        "I found the exact Articles you mentioned. I'm showing only those, not unrelated matches.",
        "",
    ]
    for doc in docs:
        parts.append(f"#### Article {doc['number']}: {doc['title']}")
        if doc["part"]:
            parts.append(f"*{doc['part']}*")
        parts.append("")
        parts.append(doc["content"])
        parts.append("")
    parts.append("**Disclaimer:** This is general information, not legal advice.")
    return "\n".join(parts).strip()


def _topic_answer(question: str, docs: list[dict]) -> str:
    grounded = _grounded_article_explanation(question, docs, specific=False)
    if grounded:
        return grounded

    parts = [
        "### Closest matching Constitutional Articles",
        "",
        "I found these Articles as the strongest matches for your question. Tap the Article chips above to inspect the original text quickly.",
        "",
    ]

    for index, doc in enumerate(docs, start=1):
        parts.append(f"{index}. **Article {doc['number']}: {doc['title']}**")
        if doc["part"]:
            parts.append(f"   - Part: *{doc['part']}*")
        preview = doc["content"].replace("\n", " ").strip()
        if len(preview) > 420:
            preview = preview[:420].rsplit(" ", 1)[0] + "..."
        parts.append(f"   - Relevant text: {preview}")
        parts.append("")

    parts.append(
        "If you want, ask a follow-up like \"explain Article 21 simply\" or \"what is the doubt in Article 14?\" and I'll focus only on that Article."
    )
    parts.append("")
    parts.append("**Disclaimer:** This is general information, not legal advice.")
    return "\n".join(parts).strip()


def generate_answer(question: str, retrieved_docs: list):
    """
    Generates an intent-aware response:
    - Friendly chat/general questions: no forced constitutional citations.
    - Exact Article questions: only the requested Article(s).
    - Topic questions: best matching Articles, clearly shown.
    - Article doubts: plain-language explanation grounded in that Article.
    """
    question = question.strip()
    requested_articles = extract_article_numbers(question)

    if should_answer_without_retrieval(question):
        return _general_answer(question)

    docs = _normalise_docs(retrieved_docs)

    if requested_articles:
        requested_set = set(requested_articles)
        docs = [doc for doc in docs if doc["number"].upper() in requested_set]

        if not docs:
            missing = ", ".join(f"Article {number}" for number in requested_articles)
            return {
                "answer": (
                    f"I could not find {missing} in the indexed Constitution text.\n\n"
                    "Please check the Article number and try again, for example: \"Article 21\" or \"Explain Article 14\"."
                ),
                "articles_cited": [],
                "retrieved_articles": [],
            }

        grounded = _grounded_article_explanation(question, docs, specific=True)
        answer = grounded or _specific_article_answer(question, docs)
        return {
            "answer": answer,
            "articles_cited": _article_citations(docs),
            "retrieved_articles": _retrieved_articles(docs),
        }

    if not docs:
        if not _has_constitutional_intent(question):
            return _general_answer(question)

        if LEGAL_BUT_NON_CONSTITUTION_PATTERN.search(question):
            answer = (
                "This looks more like a statutory/legal-procedure question than a direct Constitution Article question.\n\n"
                "The Constitution gives broad rights and institutional principles, while offences, bail, FIRs, contracts, property disputes, and similar matters usually come from separate statutes such as the BNS/IPC, CrPC/BNSS, or other laws.\n\n"
                "Ask me a constitutional angle like \"which Article protects personal liberty?\" and I'll map the closest Articles clearly.\n\n"
                "**Disclaimer:** This is general information, not legal advice."
            )
        else:
            answer = (
                "I could not find a strong matching Article from the Constitution for that question.\n\n"
                "Try asking with a constitutional keyword, for example: \"right to equality\", \"freedom of speech\", \"Article 21\", or \"fundamental duties\"."
            )
        return {
            "answer": answer,
            "articles_cited": [],
            "retrieved_articles": [],
        }

    # Drop very weak matches unless all results are weak; this keeps broad-topic results useful.
    strong_docs = [doc for doc in docs if doc.get("score", 0.0) >= 0.12]
    docs_to_use = strong_docs or docs[:4]

    return {
        "answer": _topic_answer(question, docs_to_use),
        "articles_cited": _article_citations(docs_to_use),
        "retrieved_articles": _retrieved_articles(docs_to_use),
    }
