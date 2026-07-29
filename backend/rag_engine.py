from ingester import get_vector_store
from config import settings

# Concise prompt that fits within flan-t5 token limits for single questions
ANSWER_PROMPT = """Based on the following legal text, answer the question clearly and precisely. Cite the specific Article or Section numbers.

Legal Text:
{context}

Question: {question}

Answer:"""

# Prompt to convert follow-up questions into standalone queries
REFORMULATE_PROMPT = """Given the conversation history and a follow-up question, rewrite the follow-up question to be a standalone search query that contains all necessary context. Do not answer the question, just rewrite it.

History:
{history}

Follow-up Question: {question}

Standalone Query:"""

# Prompt to answer follow-up questions using both history and retrieved context
CHAT_ANSWER_PROMPT = """Based on the following legal text and conversation history, answer the follow-up question clearly and precisely. Cite the specific Article or Section numbers.

Legal Text:
{context}

Conversation History:
{history}

Follow-up Question: {question}

Answer:"""


class HuggingFaceLLM:
    """
    A LangChain-compatible LLM wrapper around HuggingFace transformers.
    Uses google/flan-t5-base for seq2seq generation — 100% free, no API keys.
    """

    def __init__(self, model_name: str = "google/flan-t5-base", max_new_tokens: int = 512):
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        print(f"Loading HuggingFace model: {model_name} (this may take a moment on first run)...")
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        self._max_new_tokens = max_new_tokens
        # flan-t5-base supports up to 512 input tokens
        self._max_input_length = 512
        print(f"HuggingFace model '{model_name}' loaded successfully.")

    def generate(self, prompt: str) -> str:
        """Generate text from a prompt string."""
        input_ids = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self._max_input_length,
        ).input_ids
        outputs = self._model.generate(
            input_ids,
            max_new_tokens=self._max_new_tokens,
            num_beams=4,
            early_stopping=True,
            no_repeat_ngram_size=3,
        )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)


class RAGEngine:
    def __init__(self):
        self.vector_store = get_vector_store()
        self.llm = HuggingFaceLLM(
            model_name="google/flan-t5-base",
            max_new_tokens=512,
        )
        print("RAG LLM: Using local HuggingFace model (google/flan-t5-base) — FREE, no API key required")

    def _build_context_for_llm(self, relevant_docs, max_chars: int = 1200) -> str:
        """
        Build a concise context string from retrieved docs that fits within
        the model's token budget. Prioritize the top-ranked documents.
        """
        context_parts = []
        total_chars = 0
        for doc in relevant_docs:
            source = doc.metadata.get('source', 'Unknown')
            article = doc.metadata.get('article', '')
            snippet = doc.page_content.strip()

            # Truncate individual chunks if too long
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."

            part = f"[{article} from {source}]: {snippet}"
            if total_chars + len(part) > max_chars:
                break
            context_parts.append(part)
            total_chars += len(part)

        return "\n\n".join(context_parts)

    def _format_article_details(self, doc) -> dict:
        """Extract structured article details from a retrieved document."""
        source = doc.metadata.get('source', 'Unknown')
        article = doc.metadata.get('article', '')
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

        return {
            "number": number,
            "title": title,
            "part": part,
            "content": content_body,
        }

    def _build_structured_answer(self, question: str, llm_summary: str, relevant_docs) -> str:
        """
        Build a well-structured answer that combines the LLM's brief summary
        with the actual retrieved legal content. This ensures the user always
        gets the real content from the training data.
        """
        if not relevant_docs:
            return "I don't have enough information in my knowledge base to answer that question."

        answer_parts = []

        # Start with the LLM-generated contextual summary
        if llm_summary and len(llm_summary.strip()) > 10:
            answer_parts.append(llm_summary.strip())
            answer_parts.append("")

        # Add the relevant provisions from the retrieved documents
        answer_parts.append("**Relevant Provisions:**")
        answer_parts.append("")

        for i, doc in enumerate(relevant_docs):
            source = doc.metadata.get('source', 'Unknown')
            article = doc.metadata.get('article', '')
            content = doc.page_content.strip()

            # Format each retrieved provision clearly
            if source == "Constitution of India" and content.startswith("Article "):
                lines = content.split("\n")
                heading = lines[0].strip()
                part_line = ""
                body_start = 1
                if len(lines) > 1 and lines[1].strip().startswith("Part "):
                    part_line = f"*{lines[1].strip()}*"
                    body_start = 2
                body = "\n".join(lines[body_start:]).strip()

                answer_parts.append(f"**{heading}**")
                if part_line:
                    answer_parts.append(part_line)
                answer_parts.append("")
                # Show the actual legal text (truncate if very long)
                if len(body) > 800:
                    body = body[:800] + "..."
                answer_parts.append(body)
            else:
                # Criminal law sections (BNS/BNSS/BSA)
                answer_parts.append(f"**{article}** ({source})")
                answer_parts.append("")
                display_content = content
                if len(display_content) > 800:
                    display_content = display_content[:800] + "..."
                answer_parts.append(display_content)

            answer_parts.append("")

        answer_parts.append("---")
        answer_parts.append("*This information is from the indexed legal documents and is for reference only, not legal advice.*")

        return "\n".join(answer_parts)

    def query(self, question: str, chat_history: list = None) -> dict:
        # 0. Check for overlay state command matching
        from rag_pipeline.generator import should_answer_without_retrieval, _general_answer, classify_overlay_state
        state_match = classify_overlay_state(question)
        if state_match:
            print(f"Matched overlay state: {state_match['state']} for query: '{question}'")
            return {
                "answer": state_match["message"],
                "articles_cited": [],
                "retrieved_articles": [],
                "overlay_state": state_match["state"]
            }

        # 0b. Bypass retrieval for friendly/general greeting questions
        if should_answer_without_retrieval(question):
            print(f"Bypassing retrieval for general query: '{question}'")
            # General answers don't trigger overlays
            general_res = _general_answer(question)
            return {
                "answer": general_res["answer"],
                "articles_cited": [],
                "retrieved_articles": [],
                "overlay_state": None
            }

        # 1. Format chat history if present
        history_str = ""
        search_query = question

        if chat_history:
            # Take last 3 turns (6 messages) to avoid token limit overflow
            turns = chat_history[-6:]
            history_lines = []
            for m in turns:
                role = "User" if m['role'] == 'user' else "Assistant"
                content = m['content'].strip()
                if len(content) > 150:
                    content = content[:147] + "..."
                history_lines.append(f"{role}: {content}")
            history_str = "\n".join(history_lines)

            # 2. Contextualize / Reformulate query using the history
            try:
                reformulate_prompt = REFORMULATE_PROMPT.format(
                    history=history_str,
                    question=question
                )
                reformulated = self.llm.generate(reformulate_prompt).strip()
                if len(reformulated) > 5 and not reformulated.startswith("Standalone Query:"):
                    search_query = reformulated
                    print(f"Reformulated query from '{question}' to '{search_query}'")
            except Exception as e:
                print(f"Error reformulating query: {e}")

        # 3. Retrieve documents using exact match or similarity search on search_query
        from rag_pipeline.retriever import extract_article_numbers
        article_numbers = extract_article_numbers(search_query)
        
        raw_docs = []
        if article_numbers:
            from langchain_core.documents import Document
            for num in article_numbers:
                try:
                    exact_res = self.vector_store.get(
                        where={"number": {"$eq": str(num)}}
                    )
                    if exact_res and exact_res.get("documents"):
                        for doc_txt, doc_meta in zip(exact_res["documents"], exact_res["metadatas"]):
                            raw_docs.append(Document(page_content=doc_txt, metadata=doc_meta))
                except Exception as e:
                    print(f"Error querying exact match for {num}: {e}")

        # If no exact match is found, fallback to similarity search
        if not raw_docs:
            raw_docs = self.vector_store.similarity_search(
                search_query, k=settings.RETRIEVAL_K
            )

        # 4. Deduplicate by article/section identifier
        seen_keys = set()
        relevant_docs = []
        for doc in raw_docs:
            key = (
                doc.metadata.get('source', ''),
                doc.metadata.get('article', ''),
            )
            if key not in seen_keys:
                seen_keys.add(key)
                relevant_docs.append(doc)

        # 5. Build a concise context for the LLM (fits within token limit)
        context_str = self._build_context_for_llm(relevant_docs)

        # 6. Generate a brief contextual summary using the LLM
        if context_str:
            if history_str:
                prompt = CHAT_ANSWER_PROMPT.format(
                    context=context_str,
                    history=history_str,
                    question=question,
                )
            else:
                prompt = ANSWER_PROMPT.format(
                    context=context_str,
                    question=question,
                )
            llm_summary = self.llm.generate(prompt)
        else:
            llm_summary = ""

        # 7. Build the full structured answer combining LLM summary + retrieved content
        answer = self._build_structured_answer(question, llm_summary, relevant_docs)

        # 8. Build response metadata
        retrieved_articles = []
        articles_cited = []
        for doc in relevant_docs:
            source = doc.metadata.get('source', 'Unknown')
            article = doc.metadata.get('article', '')
            articles_cited.append(f"{source}: {article}")
            retrieved_articles.append(self._format_article_details(doc))

        return {
            "answer": answer,
            "articles_cited": list(dict.fromkeys(articles_cited)),
            "retrieved_articles": retrieved_articles,
            "overlay_state": None,
        }