"""
generator.py – Samaneedhi AI response generator.

Design principles
-----------------
1. Friendly assistant first: answer anything the user genuinely needs help with.
2. Harm / crime queries: respond with empathy, gentle redirection, and legal advice
   — never a cold refusal.
3. Multi-dimensional input analysis before every legal answer:
   structural · emotional · behavioural · ethical · logical
4. Precise article matching: return ONLY the article(s) the user asked for.
   Never attach "preventive" or "related" articles unless explicitly asked.
5. Accuracy target: ≥ 95 % — rely on retrieved context, never hallucinate.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parents[1]))
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BACKEND_BASE_URL = os.getenv(
    "BACKEND_BASE_URL", "https://arasamaippu-ai-backend.onrender.com"
).rstrip("/")
PROVELOCE_LOGO_URL = f"{BACKEND_BASE_URL}/proveloce_logo.png"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
ARTICLE_REFERENCE_PATTERN = re.compile(
    r'\b(?:(?:(BNS|BNSS|BSA)\s+(?:section|sec\.?)\s*(\d+[A-Z]?))'
    r'|(?:(?:section|sec\.?)\s*(\d+[A-Z]?)\s+of\s+(BNS|BNSS|BSA))'
    r'|(?:(?:article|art\.?)\s*(\d+[A-Z]?)))\b',
    re.IGNORECASE,
)

GREETING_PATTERN = re.compile(
    r"^\s*(hi+|hello+|hey+|vanakkam|namaste|good\s+(morning|afternoon|evening)"
    r"|who are you|what is your name|what'?s your name|what can you do)\b",
    re.IGNORECASE,
)

THANKS_PATTERN = re.compile(
    r"\b(thanks|thank you|great|good job|nice|excellent|awesome|super|helpful"
    r"|well done|you are good|you'?re good|love you|appreciate)\b",
    re.IGNORECASE,
)

GENERAL_CHAT_PATTERN = re.compile(
    r"\b(how are you|tell me a joke|motivate me|compliment me|say something nice"
    r"|good night|goodbye|bye|good morning|good evening)\b",
    re.IGNORECASE,
)

CONSTITUTIONAL_INTENT_PATTERN = re.compile(
    r"\b(constitution|constitutional|article|fundamental right|fundamental rights"
    r"|directive principle|dpsp|preamble|schedule|amendment|parliament|lok sabha"
    r"|rajya sabha|president|governor|supreme court|high court|writ|equality"
    r"|liberty|freedom|religion|education|citizenship|emergency|union|state"
    r"|federal|election|reservation|minority|tribe|caste|language|right to"
    r"|duties|fundamental duties|ordinance|impeachment|money bill"
    r"|finance commission)\b",
    re.IGNORECASE,
)

LEGAL_KEYWORD_PATTERN = re.compile(
    r"\b(article|section|sec|bns|bnss|bsa|law|court|judge|offence|offense"
    r"|evidence|constitution|constitutional|rights|right|duty|duties"
    r"|punishment|confinement|theft|murder|ipc|crpc|arrest|warrant|police"
    r"|magistrate|accused|appeal|judicial|fir|bail|rape|robbery|dacoity"
    r"|assault|cheating|extortion|contract|divorce|property|crime|criminal"
    r"|legal|penalty|sentence|custody|remand|chargesheet|cognizable"
    r"|non-cognizable|freedom|liberty|equality|fundamental|preamble"
    r"|parliament|president|governor|amendment|schedule|writ|habeas corpus"
    r"|directive|citizenship|reservation|minority|ordinance|lok sabha"
    r"|rajya sabha|supreme court|high court|election|emergency|federal"
    r"|union territory|state list|concurrent list|finance commission"
    r"|bharat|bharatiya|nyaya|sanhita|sakshya|nagarik suraksha"
    r"|speak|speech|expression|press|religion|conscience|movement"
    r"|profession|assemble|association|vote|property right"
    r"|life|personal liberty|privacy|dignity|education|discrimination"
    r"|untouchability|exploitation|child labour|trafficking)\b",
    re.IGNORECASE,
)

# Queries that reveal distress, intent to harm self/others, or past wrongdoing
HARM_INTENT_PATTERN = re.compile(
    r"\b("
    # Future/present intent to harm
    r"i (?:want to|am going to|will|plan to|thinking of|considering)"
    r"(?:\s+\w+){0,4}\s*(?:kill|murder|hurt|attack|harm|beat|stab|shoot|rape|steal|rob|cheat|destroy)"
    # Past actions — "I killed", "I hit", "I beat", "I stole", "I raped" etc.
    r"|i (?:killed|murdered|hurt|attacked|harmed|beat|beaten|hit|stabbed|shot|raped|stole|robbed|cheated|burnt|burned|slapped|strangled|threatened)"
    # "how to harm" queries
    r"|how (?:do i|can i|to) (?:kill|murder|hurt|attack|harm|beat|stab|shoot|rape|steal|rob|cheat|commit)"
    # Direct harm to a person
    r"|(?:kill|murder|hurt|attack|harm|beat|stab|shoot|rape|steal|rob) (?:someone|a person|my|him|her|them|neighbour|neighbor|friend|wife|husband|child)"
    # Explicit crime commission
    r"|commit (?:suicide|murder|crime|theft|robbery|fraud|rape)"
    # Self-harm / suicidal ideation
    r"|i (?:want to die|want to end my life|am suicidal|feel like dying|can't go on|cannot go on)"
    r")\b",
    re.IGNORECASE,
)

QUESTION_WORD_PATTERN = re.compile(
    r"\b(what|why|how|explain|meaning|doubt|clarify|clear|can|does|is|are"
    r"|scope|example|define|definition|tell me about)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Overlay state (UI widget states)
# ---------------------------------------------------------------------------
STATE_MESSAGES = {
    "empty": "Nothing here yet. Start exploring!",
    "loading": "Loading your content… please wait.",
    "error": "Something went wrong.",
    "offline": "You're offline. Check your connection.",
    "slow": "Network is slow, hang tight.",
    "no_results": "No results found. Try different keywords.",
    "denied": "Permission denied. Please allow access.",
    "expired": "Your session has expired. Log in again.",
    "invalid": "Please correct the errors before submitting.",
    "success": "Action completed successfully!",
}


def classify_overlay_state(question: str) -> dict | None:
    q = question.strip().lower()
    if not q:
        return None
    states = {
        "empty": ["empty", "no data", "nothing here", "blank", "empty state", "/empty"],
        "loading": ["loading", "fetching", "please wait", "spinner", "loader", "/loading"],
        "error": ["error", "failed", "crash", "wrong", "failure", "/error"],
        "offline": ["offline", "no internet", "disconnected", "no wifi", "/offline"],
        "slow": ["slow", "lag", "latency", "hang", "slow network", "/slow"],
        "no_results": ["no results", "search empty", "empty search", "zero matches", "/no_results"],
        "denied": ["denied", "blocked", "permission", "allow access", "forbidden", "/denied"],
        "expired": ["expired", "timeout", "session timeout", "session expired", "/expired"],
        "invalid": ["invalid", "form error", "correct errors", "validation error", "/invalid"],
        "success": ["success", "done", "completed", "succeeded", "ok", "/success"],
    }
    clean_q = q[1:] if q.startswith("/") else q
    best_match, max_score = None, 0.0
    for state_name, keywords in states.items():
        for kw in keywords:
            if clean_q == kw:
                score = 1.0
            elif kw in clean_q or clean_q in kw:
                score = len(kw) / max(len(clean_q), 1)
            else:
                continue
            if score > max_score:
                max_score, best_match = score, state_name
    if not best_match:
        for prefix in ["test state", "state", "test"]:
            if clean_q.startswith(prefix):
                target = clean_q.replace(prefix, "").strip()
                for state_name in states:
                    if target in state_name or state_name in target:
                        max_score, best_match = 0.9, state_name
                        break
    if max_score >= 0.8 and best_match:
        return {"state": best_match, "message": STATE_MESSAGES[best_match]}
    if q.startswith("/") or q.startswith("state ") or q.startswith("test "):
        return {"state": "error", "message": STATE_MESSAGES["error"]}
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_article_numbers(question: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []

    def _add(raw: str) -> None:
        m = re.match(r'^(BNS|BNSS|BSA)\s+SECTION\s+(\d+[A-Z]?)$', raw.upper())
        normalized = f"{m.group(1)} Section {m.group(2)}" if m else raw.upper()
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)

    standalone = re.fullmatch(r'\s*(\d{1,3}[A-Z]?)\s*', question)
    if standalone:
        return [standalone.group(1).upper()]

    for m in ARTICLE_REFERENCE_PATTERN.finditer(question):
        g1, g2, g3, g4, g5 = m.groups()
        if g1 and g2:
            _add(f"{g1.upper()} Section {g2.upper()}")
        elif g3 and g4:
            _add(f"{g4.upper()} Section {g3.upper()}")
        elif g5:
            _add(g5.upper())
    return results


def _is_legal_query(question: str) -> bool:
    """
    Returns True if the question has any legal, constitutional, or rights-related
    intent. This is intentionally broad so natural-language queries like
    "what can I do if harassed" are not wrongly rejected.
    """
    if LEGAL_KEYWORD_PATTERN.search(question):
        return True
    if CONSTITUTIONAL_INTENT_PATTERN.search(question):
        return True
    # Victim/rights natural phrasing
    victim_phrases = [
        "what can i do", "what should i do", "my rights", "i was", "someone did",
        "they did to me", "what happens if", "can i file", "can i complaint",
        "is it legal", "is it illegal", "can police", "can a person",
        "harassed me", "cheated me", "stole from me", "attacked me",
    ]
    q_lower = question.strip().lower()
    if any(p in q_lower for p in victim_phrases):
        return True
    return False


def should_answer_without_retrieval(question: str) -> bool:
    q = question.strip()
    if not q:
        return True
    if _is_legal_query(q):
        return False
    return True


def _safe_google_api_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    return "" if not key or key.lower().startswith("your_") else key


def _call_gemini(prompt: str, timeout: int = 12) -> str | None:
    api_key = _safe_google_api_key()
    if not api_key:
        return None
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta"
        f"/models/{model}:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.9,
            "maxOutputTokens": 1200,
        },
    }
    try:
        r = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
        r.raise_for_status()
        candidates = r.json().get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        return text.strip() or None
    except Exception as exc:
        print(f"Gemini call skipped: {exc}")
        return None


# ---------------------------------------------------------------------------
# Multi-dimensional input analysis
# ---------------------------------------------------------------------------

def _analyse_input(question: str) -> dict:
    """
    Performs five-dimensional analysis of the user's input.
    Returns a dict used to guide response tone, depth, and routing.
    """
    q = question.strip()
    q_lower = q.lower()

    # 1. Structural analysis – what type of query is this?
    is_specific_article = bool(ARTICLE_REFERENCE_PATTERN.search(q))
    is_topical = bool(CONSTITUTIONAL_INTENT_PATTERN.search(q) and not is_specific_article)
    is_definitional = bool(re.search(
        r'\b(what is|what are|define|definition|meaning of|explain)\b', q_lower
    ))
    is_procedural = bool(re.search(
        r'\b(how to|how do|procedure|process|steps|can i|can a person)\b', q_lower
    ))
    is_harm_query = bool(HARM_INTENT_PATTERN.search(q))
    is_general_chat = bool(
        GREETING_PATTERN.search(q) or GENERAL_CHAT_PATTERN.search(q)
        or THANKS_PATTERN.search(q)
    )

    structural = (
        "specific_article" if is_specific_article
        else "harm_query" if is_harm_query
        else "general_chat" if is_general_chat
        else "definitional" if is_definitional
        else "procedural" if is_procedural
        else "topical" if is_topical
        else "general"
    )

    # 2. Emotional analysis – detect distress, fear, anger, curiosity
    distress_words = ["help", "scared", "afraid", "worried", "stress", "victim",
                      "harassed", "tortured", "hurt", "pain", "cry", "depressed",
                      "suicid", "die", "end my life", "hopeless"]
    anger_words = ["angry", "furious", "rage", "hate", "revenge", "punish",
                   "destroy", "kill", "attack"]
    curiosity_words = ["curious", "interesting", "wonder", "explore", "learn",
                       "understand", "know more", "tell me"]

    emotional_tone = "neutral"
    if any(w in q_lower for w in distress_words):
        emotional_tone = "distressed"
    elif any(w in q_lower for w in anger_words):
        emotional_tone = "agitated"
    elif any(w in q_lower for w in curiosity_words):
        emotional_tone = "curious"

    # 3. Behavioural analysis – is the user a victim, offender, or researcher?
    victim_indicators = ["i was", "someone did", "they did", "he did", "she did",
                         "attacked me", "harassed me", "cheated me", "stole from",
                         "what are my rights", "can i file", "can i complaint"]
    offender_indicators = ["i did", "i committed", "i stole", "i hit", "i hurt",
                           "i killed", "i beat", "i cheated", "what will happen to me",
                           "will i go to jail", "can i get bail"]
    research_indicators = ["what is the punishment", "what does the law say",
                           "explain section", "explain article", "definition",
                           "for a project", "studying", "research"]

    behavioural_role = "general_user"
    if any(w in q_lower for w in victim_indicators):
        behavioural_role = "victim"
    elif any(w in q_lower for w in offender_indicators):
        behavioural_role = "offender_or_accused"
    elif any(w in q_lower for w in research_indicators):
        behavioural_role = "researcher"

    # 4. Ethical analysis – does the query involve a potential wrong?
    ethical_concern = "none"
    if is_harm_query:
        ethical_concern = "potential_harm"
    elif behavioural_role == "offender_or_accused":
        ethical_concern = "past_wrong"
    elif behavioural_role == "victim":
        ethical_concern = "rights_violation"

    # 5. Logical analysis – is the question well-formed and answerable?
    word_count = len(q.split())
    has_enough_context = word_count >= 3
    logical_quality = "clear" if has_enough_context else "vague"

    return {
        "structural": structural,
        "emotional_tone": emotional_tone,
        "behavioural_role": behavioural_role,
        "ethical_concern": ethical_concern,
        "logical_quality": logical_quality,
        "is_harm_query": is_harm_query,
        "is_specific_article": is_specific_article,
        "is_general_chat": is_general_chat,
        "word_count": word_count,
    }


# ---------------------------------------------------------------------------
# Harm / crime query handler — empathy + legal advice, never a cold refusal
# ---------------------------------------------------------------------------

def _harm_query_response(question: str, analysis: dict) -> dict:
    """
    When someone asks about committing harm OR reveals they already did something,
    respond with empathy, gentle redirection, and actionable legal guidance.
    Never lecture coldly or refuse outright.
    """
    q_lower = question.strip().lower()

    # Suicidal / self-harm intent
    if any(phrase in q_lower for phrase in [
        "want to die", "end my life", "suicidal", "feel like dying", "kill myself"
    ]):
        answer = (
            "I can hear that you're going through something really painful right now, "
            "and I'm genuinely glad you reached out.\n\n"
            "**Please know: you are not alone, and help is available right now.**\n\n"
            "🆘 **iCall Helpline (India):** 9152987821\n"
            "🆘 **Vandrevala Foundation:** 1860-2662-345 (24×7)\n"
            "🆘 **National Helpline:** 14416 (iCall, free)\n\n"
            "If you're in immediate danger, please call **112** (Emergency Services).\n\n"
            "Talking to someone trained to listen can make a real difference. "
            "You deserve support — please reach out to them right now. 💙"
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    # Past wrongdoing — person may have committed an offence
    if analysis["behavioural_role"] == "offender_or_accused":
        answer = (
            "It takes courage to seek help, and I want to give you honest guidance.\n\n"
            "**Here's what you should know:**\n\n"
            "- Every person in India has the right to legal representation under "
            "**Article 22** of the Constitution. You cannot be denied a lawyer.\n"
            "- If you've been involved in something that may be unlawful, the most "
            "important step is to **consult a qualified advocate immediately** — "
            "they are bound by confidentiality and can advise you on your options.\n"
            "- Acting transparently and cooperating with legal processes usually leads "
            "to better outcomes than avoidance.\n\n"
            "**Practical advice:**\n"
            "- Do not discuss details with anyone except your lawyer.\n"
            "- You have the right to remain silent until you have legal counsel "
            "(protected under **Article 20(3)** — right against self-incrimination).\n"
            "- Legal Aid is free if you cannot afford a lawyer: "
            "contact your nearest **District Legal Services Authority (DLSA)**.\n\n"
            "I'm here to help you understand the law — not to judge you. "
            "If you'd like to know what a specific section or article says, just ask. 🙏"
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    # Intent to harm others — redirect with empathy and legal consequence awareness
    answer = (
        "I can sense there's something difficult behind this question, "
        "and I want to respond thoughtfully rather than just refuse.\n\n"
        "**I'm not able to assist with causing harm to anyone** — "
        "but I genuinely want to help you with what's underneath this.\n\n"
        "**If you're in a conflict or dispute**, the law offers real solutions:\n"
        "- **Article 21** guarantees every person the right to life and dignity — "
        "including you and those around you.\n"
        "- Civil disputes can be resolved through courts, mediation, or lok adalats.\n"
        "- Domestic situations have protection under the Protection of Women from "
        "Domestic Violence Act and BNS provisions.\n\n"
        "**Advice:**\n"
        "- Talk to someone you trust, or call a counsellor.\n"
        "- If you feel in danger, call **112** immediately.\n"
        "- Legal help is free at your nearest **DLSA** (District Legal Services Authority).\n\n"
        "Tell me what's really going on — I'll do my best to point you toward "
        "the right legal path. 💙"
    )
    return {"answer": answer, "articles_cited": [], "retrieved_articles": []}


# ---------------------------------------------------------------------------
# General / greeting / chat responses
# ---------------------------------------------------------------------------

def _friendly_general_answer(question: str, analysis: dict) -> dict:
    """
    Handles greetings, thanks, general chat, and truly off-topic questions
    with a warm, helpful personality.
    """
    q = question.strip().lower()

    if GREETING_PATTERN.search(q):
        answer = (
            "Hi there! 👋 I'm **Samaneedhi AI** — your friendly guide to the "
            "Constitution of India and Indian Laws (BNS, BNSS, BSA).\n\n"
            f"![ProVeloce Logo]({PROVELOCE_LOGO_URL}) *A Product by ProVeloce*\n\n"
            "Here are some things you can ask me:\n\n"
            "- \"What is Article 21?\"\n"
            "- \"Explain BNS Section 103\"\n"
            "- \"What are Fundamental Rights?\"\n"
            "- \"What is the punishment for theft under BNS?\"\n\n"
            "I'm here to make Indian law clear, approachable, and useful for you. "
            "What would you like to know? 😊"
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    if THANKS_PATTERN.search(q):
        answer = (
            "That really means a lot — thank you! 😊\n\n"
            "Helping you understand your rights and the law is exactly what I'm here for. "
            "Feel free to ask anything else anytime."
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    if "how are you" in q:
        answer = (
            "I'm doing great, thank you for asking! 😊 "
            "Ready and focused to help you with anything related to Indian law.\n\n"
            "What legal question can I answer for you today?"
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    if any(phrase in q for phrase in ["good night", "goodbye", "bye", "see you"]):
        answer = (
            "Take care! 👋 Come back whenever you have a legal question. "
            "I'm always here to help. 😊"
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    if "motivate me" in q or "say something nice" in q or "compliment me" in q:
        answer = (
            "You're doing something important just by wanting to understand the law. "
            "Legal awareness is a superpower — most people never bother. Keep going! 💪\n\n"
            "Now, is there a legal question I can help you with?"
        )
        return {"answer": answer, "articles_cited": [], "retrieved_articles": []}

    # Truly off-topic (not legal, not greeting) — be helpful and redirect warmly
    prompt = (
        "You are Samaneedhi AI, a warm and friendly legal assistant for Indian laws "
        "(A Product by ProVeloce). The user has asked a question that is NOT about "
        "Indian law or the Constitution.\n\n"
        "Respond in a friendly, warm tone. Acknowledge their question briefly, then "
        "gently let them know you specialise in Indian law (Constitution, BNS, BNSS, BSA) "
        "and invite them to ask a legal question. Keep it to 3-4 sentences maximum. "
        "Do NOT be dismissive or robotic.\n\n"
        f"User question: {question}"
    )
    llm_answer = _call_gemini(prompt)
    answer = llm_answer or (
        "That's an interesting question! I specialise in Indian law — the Constitution, "
        "BNS, BNSS, and BSA. I might not be the best guide for that topic, but if you "
        "have any legal questions, I'm all yours. 😊"
    )
    return {"answer": answer, "articles_cited": [], "retrieved_articles": []}


# ---------------------------------------------------------------------------
# Document normalisation helpers
# ---------------------------------------------------------------------------

def _doc_parts(doc: Any) -> tuple[dict, str, float]:
    if hasattr(doc, "metadata"):
        meta = doc.metadata or {}
        content = getattr(doc, "page_content", "") or ""
        score = getattr(doc, "score", 1.0)
    elif isinstance(doc, dict):
        meta = doc.get("metadata") or {
            "number": doc.get("number", ""),
            "title": doc.get("title", ""),
            "part": doc.get("part", ""),
            "type": doc.get("type", "article"),
        }
        content = doc.get("content", "") or doc.get("page_content", "")
        score = doc.get("score", 1.0)
    else:
        meta, content, score = {}, "", 1.0
    return meta, content, float(score or 0.0)


def _clean_article_content(content: str, meta: dict) -> str:
    doc_num = str(meta.get("number", "")).strip()
    doc_title = str(meta.get("title", "")).strip()
    doc_part = str(meta.get("part", "")).strip()
    cleaned = (content or "").strip()
    for pattern in [
        rf"^\s*Article\s+{re.escape(doc_num)}\s*:\s*{re.escape(doc_title)}\s*",
        rf"^\s*Article\s+{re.escape(doc_num)}\s*[.\-:]\s*{re.escape(doc_title)}\s*",
        rf"^\s*{re.escape(doc_num)}\.\s*{re.escape(doc_title)}[.\-]*\s*",
    ]:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    if doc_part:
        cleaned = re.sub(
            rf"^\s*Part:\s*{re.escape(doc_part)}\s*", "", cleaned, flags=re.IGNORECASE
        ).strip()
    return cleaned


def _normalise_docs(retrieved_docs: list) -> list[dict]:
    docs: list[dict] = []
    seen: set[tuple] = set()
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
        docs.append({
            "number": number,
            "title": str(meta.get("title", "")).strip(),
            "part": str(meta.get("part", "")).strip(),
            "type": doc_type,
            "content": _clean_article_content(content, meta),
            "score": score,
        })
    return docs


def _article_citations(docs: list[dict]) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for doc in docs:
        label = (
            f"{doc['type'].upper()} Section {doc['number']}"
            if doc["type"] != "article"
            else f"Article {doc['number']}"
        )
        if label not in seen:
            seen.add(label)
            citations.append(label)
    return citations


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


# ---------------------------------------------------------------------------
# Precise legal answer builders
# ---------------------------------------------------------------------------

def _build_grounded_prompt(question: str, docs: list[dict], analysis: dict) -> str:
    """
    Constructs a highly precise prompt for Gemini that enforces:
    - Only answer from provided context
    - Return ONLY the requested article/section — no extras
    - Multi-dimensional awareness (victim/offender/researcher tone)
    - Accuracy over verbosity
    """
    context = "\n\n".join(
        f"[{doc['type'].upper()} {doc['number']}]: {doc['title']}\n"
        f"Part: {doc['part']}\n"
        f"Text:\n{doc['content']}"
        for doc in docs
    )

    role_note = ""
    if analysis["behavioural_role"] == "victim":
        role_note = (
            "The user appears to be a victim or someone whose rights may have been violated. "
            "Be empathetic, highlight their rights clearly, and mention they can seek legal aid."
        )
    elif analysis["behavioural_role"] == "offender_or_accused":
        role_note = (
            "The user may be an accused or someone who has committed an offence. "
            "Explain the law factually and remind them of their right to legal counsel."
        )
    elif analysis["behavioural_role"] == "researcher":
        role_note = (
            "The user is likely a student or researcher. Be precise and educational."
        )

    tone_note = ""
    if analysis["emotional_tone"] == "distressed":
        tone_note = "The user sounds distressed. Be warm and reassuring in tone."
    elif analysis["emotional_tone"] == "agitated":
        tone_note = "The user sounds agitated. Be calm, clear, and non-judgmental."

    query_type_note = (
        "The user asked for a SPECIFIC article/section by number. "
        "Return ONLY that article's content. Do NOT add other related articles "
        "or prevention measures unless explicitly asked."
        if analysis["is_specific_article"]
        else
        "Answer the topic question using only the most relevant articles in the context."
    )

    return (
        "You are Samaneedhi AI, a precise and friendly Indian legal assistant "
        "(A Product by ProVeloce). Your accuracy must be above 95%%.\n\n"
        "STRICT RULES:\n"
        "1. Answer ONLY using the provided context. Never use external knowledge.\n"
        "2. If the answer is not in the context, say exactly: "
        "'I could not find this in the indexed legal files.'\n"
        "3. Do NOT invent article numbers, section numbers, or legal provisions.\n"
        "4. Do NOT add preventive articles or related sections unless the user asked for them.\n"
        "5. Quote the exact legal text where relevant, then explain it plainly.\n"
        "6. End with a short disclaimer: this is general information, not legal advice.\n\n"
        f"QUERY TYPE: {query_type_note}\n"
        f"USER ROLE NOTE: {role_note}\n"
        f"TONE NOTE: {tone_note}\n\n"
        f"User question: {question}\n\n"
        f"Context:\n{context}"
    )


def _grounded_answer(question: str, docs: list[dict], analysis: dict) -> str | None:
    if not docs:
        return None
    prompt = _build_grounded_prompt(question, docs, analysis)
    answer = _call_gemini(prompt)
    if not answer:
        return None
    # Ensure specific-article responses are properly headed
    if analysis["is_specific_article"] and len(docs) == 1:
        doc = docs[0]
        label = (
            f"Section {doc['number']}"
            if doc["type"] != "article"
            else f"Article {doc['number']}"
        )
        if label not in answer and doc["number"] not in answer:
            answer = f"### {label}: {doc['title']}\n\n{answer}"
    return answer


def _fallback_specific_answer(question: str, docs: list[dict]) -> str:
    """Used when Gemini is unavailable — formats the raw retrieved text cleanly."""
    if len(docs) == 1:
        doc = docs[0]
        is_section = doc["type"] != "article"
        label = f"Section {doc['number']}" if is_section else f"Article {doc['number']}"
        heading = f"### {label}: {doc['title']}"
        part_line = f"*{doc['part']}*\n\n" if doc["part"] else ""
        intro = (
            "**Direct explanation:** Here is the exact text of this provision.\n\n"
            if bool(QUESTION_WORD_PATTERN.search(question))
            else "**Exact text:**\n\n"
        )
        return (
            f"{heading}\n\n"
            f"{part_line}"
            f"{intro}"
            f"{doc['content']}\n\n"
            "**Disclaimer:** This is general information, not legal advice. "
            "For a specific legal problem, please consult a qualified advocate."
        )

    parts = ["### Requested provisions\n"]
    for doc in docs:
        is_section = doc["type"] != "article"
        label = f"Section {doc['number']}" if is_section else f"Article {doc['number']}"
        parts.append(f"#### {label}: {doc['title']}")
        if doc["part"]:
            parts.append(f"*{doc['part']}*")
        parts.append("")
        parts.append(doc["content"])
        parts.append("")
    parts.append(
        "**Disclaimer:** This is general information, not legal advice. "
        "Consult a qualified advocate for specific problems."
    )
    return "\n".join(parts).strip()


def _fallback_topic_answer(question: str, docs: list[dict]) -> str:
    """Used when Gemini is unavailable — lists top matches for topic questions."""
    parts = ["### Most relevant provisions found\n"]
    for i, doc in enumerate(docs, 1):
        is_section = doc["type"] != "article"
        label = f"Section {doc['number']}" if is_section else f"Article {doc['number']}"
        parts.append(f"{i}. **{label}: {doc['title']}**")
        if doc["part"]:
            parts.append(f"   *{doc['part']}*")
        preview = doc["content"].replace("\n", " ").strip()
        if len(preview) > 400:
            preview = preview[:400].rsplit(" ", 1)[0] + "…"
        parts.append(f"   {preview}")
        parts.append("")
    parts.append(
        "Ask a follow-up like \"explain Article 21 in simple terms\" "
        "to get a detailed explanation of any specific provision.\n\n"
        "**Disclaimer:** This is general information, not legal advice."
    )
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Top-level generate_answer entry point
# ---------------------------------------------------------------------------

def generate_answer(question: str, retrieved_docs: list) -> dict:
    """
    Main entry point called by the /ask endpoint.

    Flow:
    1.  Multi-dimensional input analysis
    2.  Harm/distress queries → empathetic handler with advice
    3.  General chat / greetings → friendly handler
    4.  Specific article/section query → return ONLY that article, precisely
    5.  Topic/conceptual query → best matching articles with grounded explanation
    6.  No docs found → helpful guidance, not a cold refusal
    """
    question = (question or "").strip()
    if not question:
        return {
            "answer": "Please type a question and I'll do my best to help! 😊",
            "articles_cited": [],
            "retrieved_articles": [],
        }

    # --- Step 1: multi-dimensional analysis ---
    analysis = _analyse_input(question)

    # --- Step 2: harm / distress / offender queries ---
    # Trigger harm handler when HARM_INTENT_PATTERN fires OR when the analysis
    # identifies an offender/accused role (e.g. "I hit someone", "I stole…")
    if analysis["is_harm_query"] or analysis["ethical_concern"] in (
        "potential_harm", "past_wrong"
    ):
        return _harm_query_response(question, analysis)

    # --- Step 3: general chat ---
    if analysis["is_general_chat"] or should_answer_without_retrieval(question):
        return _friendly_general_answer(question, analysis)

    # --- Step 4 & 5: legal queries ---
    requested_articles = extract_article_numbers(question)
    docs = _normalise_docs(retrieved_docs)

    # --- Specific article(s) requested ---
    if requested_articles:
        requested_set = {n.upper() for n in requested_articles}
        # Filter docs to ONLY the requested articles — no extras
        matched_docs = [d for d in docs if d["number"].upper() in requested_set]

        if not matched_docs:
            missing = ", ".join(
                f"Article {n}" if not re.match(r'^(BNS|BNSS|BSA)', n, re.I)
                else n
                for n in requested_articles
            )
            return {
                "answer": (
                    f"I couldn't find **{missing}** in the indexed legal files.\n\n"
                    "Please double-check the number. Examples of valid queries:\n"
                    "- \"Article 21\"\n"
                    "- \"BNS Section 103\"\n"
                    "- \"BNSS Section 187\""
                ),
                "articles_cited": [],
                "retrieved_articles": [],
            }

        answer = (
            _grounded_answer(question, matched_docs, analysis)
            or _fallback_specific_answer(question, matched_docs)
        )
        return {
            "answer": answer,
            "articles_cited": _article_citations(matched_docs),
            "retrieved_articles": _retrieved_articles(matched_docs),
        }

    # --- Topic / conceptual query ---
    if not docs:
        # No docs retrieved — give helpful guidance
        role_note = ""
        if analysis["behavioural_role"] == "victim":
            role_note = (
                "\n\nIf your rights have been violated, you can:\n"
                "- File a complaint at the nearest police station\n"
                "- Approach the **State Human Rights Commission**\n"
                "- Get free legal aid from your nearest **DLSA**"
            )

        return {
            "answer": (
                "I couldn't find a strong match in the indexed legal files for that question.\n\n"
                "Try rephrasing with a specific term, for example:\n"
                "- \"right to equality\"\n"
                "- \"freedom of speech\"\n"
                "- \"Article 19\"\n"
                "- \"BNS Section 85\""
                f"{role_note}"
            ),
            "articles_cited": [],
            "retrieved_articles": [],
        }

    # Use only docs with a meaningful relevance score
    strong_docs = [d for d in docs if d.get("score", 0.0) >= 0.12]
    docs_to_use = strong_docs[:5] if strong_docs else docs[:4]

    answer = (
        _grounded_answer(question, docs_to_use, analysis)
        or _fallback_topic_answer(question, docs_to_use)
    )
    return {
        "answer": answer,
        "articles_cited": _article_citations(docs_to_use),
        "retrieved_articles": _retrieved_articles(docs_to_use),
    }
