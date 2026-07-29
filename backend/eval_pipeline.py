import sys
import types
from unittest.mock import MagicMock

# Monkeypatch vertexai import conflict in Ragas/LangChain
try:
    from langchain_google_vertexai import ChatVertexAI
except ImportError:
    ChatVertexAI = MagicMock

module_name = 'langchain_community.chat_models.vertexai'
mod = types.ModuleType(module_name)
mod.ChatVertexAI = ChatVertexAI
sys.modules[module_name] = mod

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from datasets import Dataset

# Load environment variables
load_dotenv()

# Step 1: Ingestion
print("Step 1: Loading PDF documents from 'data' folder...")
DATA_DIR = Path(__file__).resolve().parent / "data"
pdf_files = list(DATA_DIR.glob("*.pdf"))

if not pdf_files:
    print(f"Error: No PDF files found in {DATA_DIR}!")
    exit(1)

print(f"Found {len(pdf_files)} PDF files to evaluate:")
for f in pdf_files:
    print(f" - {f.name}")

# Import LangChain components safely
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma

raw_docs = []
for pdf_file in pdf_files:
    try:
        loader = PyPDFLoader(str(pdf_file))
        pages = loader.load()
        print(f"Parsing {pdf_file.name} ({len(pages)} pages total, keeping first 15)...")
        raw_docs.extend(pages[:15])
    except Exception as e:
        print(f"Warning: Failed to load {pdf_file.name}: {e}")

print(f"Successfully loaded {len(raw_docs)} sample pages for evaluation.")

# Step 2: Text Splitting
print("\nStep 2: Splitting text into overlapping chunks...")
# 512 characters with 50 overlap to maintain semantic continuity
text_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
chunks = text_splitter.split_documents(raw_docs)
print(f"Created {len(chunks)} text chunks.")

# Step 3: Embedding & Vector Storage
print("\nStep 3: Generating embeddings and storing in Chroma vector store...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
# Use a temporary in-memory Chroma DB for evaluation
vector_db = Chroma.from_documents(chunks, embeddings)
print("Vector database initialized successfully.")

# Step 4: Retriever Component
print("\nStep 4: Initializing retriever...")
retriever = vector_db.as_retriever(search_kwargs={"k": 4})

# Step 5: Test Questions
print("\nStep 5: Loading evaluation test questions...")
test_questions = [
    "What is Article 21 of the Constitution of India?",
    "What does BNS Section 15 say about acts done by a Judge?",
    "What are the fundamental duties under the Constitution?",
    "Explain the limits of solitary confinement under BNS.",
    "What is the definition of theft under the criminal code?"
]

# Step 6: Data Capture
print("\nStep 6: Executing RAG pipeline to capture context and generate answers...")
# Initialize our local LLM generator (google/flan-t5-base)
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

print("Loading local generator model: google/flan-t5-base...")
model_name = "google/flan-t5-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

def generate_local_answer(question: str, context: str) -> str:
    prompt = f"Context: {context}\n\nQuestion: {question}\n\nAnswer:"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=256, num_beams=4, early_stopping=True)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

captured_data = []

for idx, q in enumerate(test_questions):
    print(f"\nProcessing question {idx+1}/{len(test_questions)}: '{q}'")
    # Retrieve relevant contexts
    retrieved_docs = retriever.invoke(q)
    contexts = [doc.page_content for doc in retrieved_docs]
    
    # Generate response
    context_text = "\n".join(contexts)
    response = generate_local_answer(q, context_text)
    
    # Step 7: Schema Mapping
    data_item = {
        "user_input": q,
        "retrieved_contexts": contexts,
        "response": response,
        "reference": "Reference answer not available."
    }
    captured_data.append(data_item)
    print(f"Generated Answer: {response[:150]}...")

# Step 8: Dataset Conversion
print("\nStep 8: Converting captured data into Hugging Face Dataset...")
hf_dataset = Dataset.from_list(captured_data)
print("Hugging Face Dataset created successfully.")

# Step 9: Ragas Evaluation
print("\nStep 9: Running Ragas Evaluation...")
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

# Setup evaluator LLM based on environment keys
evaluator_llm = None
evaluator_embeddings = embeddings

openai_key = os.getenv("OPENAI_API_KEY", "").strip()
google_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

if google_key:
    print("Using Google Gemini API key as the evaluator LLM...")
    from langchain_google_genai import ChatGoogleGenerativeAI
    evaluator_llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=google_key)
elif openai_key:
    print("Using OpenAI API key as the evaluator LLM...")
    from langchain_openai import ChatOpenAI
    evaluator_llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key)
else:
    print("Warning: No Google or OpenAI API keys found in .env!")
    print("Evaluation requires a judge LLM to compute scores. Attempting to load local evaluator LLM...")
    from langchain_community.llms import HuggingFacePipeline
    from transformers import pipeline
    eval_pipe = pipeline("text2text-generation", model=model, tokenizer=tokenizer, max_new_tokens=256)
    evaluator_llm = HuggingFacePipeline(pipeline=eval_pipe)

try:
    print("Evaluating RAG dataset metrics (Faithfulness, Answer Relevancy, Context Precision)...")
    results = evaluate(
        dataset=hf_dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings
    )
    
    # Store results
    print("\n--- EVALUATION RESULTS ---")
    print(results)
    
    results_df = results.to_pandas()
    
    # Save to CSV and JSON
    output_csv = DATA_DIR / "evaluation_results.csv"
    output_json = DATA_DIR / "evaluation_results.json"
    
    results_df.to_csv(output_csv, index=False)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(captured_data, f, indent=2)
        
    print(f"\nSaved structured evaluation scores to: {output_csv}")
    print(f"Saved raw execution data to: {output_json}")

except Exception as e:
    print(f"\nRagas Evaluation encountered an error during LLM grading: {e}")
    print("This is usually due to local model token constraints on Ragas grading templates.")
    print("Saving captured RAG data to data/captured_rag_data.json...")
    output_json = DATA_DIR / "captured_rag_data.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(captured_data, f, indent=2)
    print(f"Captured data saved to: {output_json}")
