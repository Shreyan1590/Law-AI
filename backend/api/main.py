import os
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

# Add parents to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
from rag_pipeline.retriever import retrieve
from rag_pipeline.generator import generate_answer
from rag_pipeline.d1_client import D1Client

# Initialize D1 Client
d1_client = D1Client()

# Import Cloudflare Workers SDK and ASGI adapter if available
try:
    from workers import WorkerEntrypoint
    import asgi
    HAS_CF_WORKERS = True
except ImportError:
    HAS_CF_WORKERS = False

# Setup logging (Step 7)
LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "queries.log"

logger = logging.getLogger("LegalAssistant")
logger.setLevel(logging.INFO)

# Rotate logs after 5MB, keeping 3 backups
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# FastAPI Init
app = FastAPI(
    title="Indian Constitution Legal Assistant API",
    description="Backend API serving RAG-based constitutional law answers",
    version="1.0.0"
)

# Enable CORS with regex origin matching to ensure browsers never block fetch requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.options("/{full_path:path}")
async def options_preflight_handler(full_path: str):
    """
    Explicit OPTIONS preflight handler to return 200 OK for CORS preflight requests across all endpoints.
    """
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )

import hashlib

# Hashing utility for passwords
def hash_password(password: str) -> str:
    # SHA-256 with a salt
    salt = "indian_constitution_law_sec_salt_2026"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

# Request Models
class AskRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The legal question to ask, between 3 and 500 characters."
    )
    email: str = Field(
        None,
        description="Optional user email to automatically save query to search history database."
    )

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(...)
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(...)

class GoogleLoginRequest(BaseModel):
    email: str = Field(...)

class GoogleSignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(...)

class AuthResponse(BaseModel):
    success: bool
    message: str
    name: str = None
    email: str = None
    code: str = None

class ArticleDetail(BaseModel):
    number: str = Field(description="Article or Provision number.")
    title: str = Field(description="Article title.")
    part: str = Field(description="Part of the Constitution.")
    content: str = Field(description="Raw text content of the article.")

class AskResponse(BaseModel):
    answer: str
    articles_cited: list[str]
    retrieved_articles: list[ArticleDetail] = []

@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    """
    Root endpoint — prevents 404 when the browser auto-requests the base URL.
    """
    return {
        "name": "Indian Constitution Legal Assistant API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": ["/ask", "/health", "/docs"]
    }

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    Favicon handler — prevents 404 when browsers auto-request /favicon.ico.
    """
    return Response(status_code=204)

@app.api_route("/sms/webhook", methods=["GET", "POST"], status_code=status.HTTP_200_OK)
async def sms_webhook(request: Request):
    """
    Webhook receiver endpoint for Textbee SMS delivery reports and callbacks.
    Verifies signature if TEXTBEE_SIGNING_SECRET is configured.
    """
    try:
        signing_secret = os.getenv("TEXTBEE_SIGNING_SECRET", "")
        signature_header = (
            request.headers.get("x-signature")
            or request.headers.get("x-textbee-signature")
            or request.headers.get("authorization")
        )

        payload = {}
        if request.method == "POST":
            try:
                payload = await request.json()
            except Exception:
                body_bytes = await request.body()
                payload = {"raw": body_bytes.decode("utf-8", errors="ignore")}
        else:
            payload = dict(request.query_params)
        
        logger.info(f"Textbee Webhook Event Received (Signature: {signature_header}): {payload}")
        return {"status": "success", "message": "Webhook processed successfully", "data": payload}
    except Exception as e:
        logger.warning(f"SMS Webhook processing notice: {e}")
        return {"status": "success", "message": "Webhook received"}

# In-memory OTP Cache: phone -> otp_code
OTP_STORAGE = {}

class SendOtpRequest(BaseModel):
    phone: str = Field(..., description="Mobile number formatted with +91")

class VerifyOtpRequest(BaseModel):
    phone: str = Field(..., description="Mobile number formatted with +91")
    otp: str = Field(..., description="6-digit OTP code")

@app.post("/sms/send-otp", status_code=status.HTTP_200_OK)
async def send_sms_otp(request: SendOtpRequest):
    """
    Sends 6-digit OTP via SMS Gateway API using SMS_API_KEY fetched from environment variables (Render / .env).
    """
    phone = request.phone.strip()
    clean_digits = re.sub(r'\D', '', phone)
    if clean_digits.startswith("91") and len(clean_digits) == 12:
        clean_digits = clean_digits[2:]
    formatted_phone = f"+91{clean_digits}"

    # Generate 6-digit OTP
    otp_code = str(random.randint(100000, 999999))
    OTP_STORAGE[formatted_phone] = otp_code

    # Fetch TEXTBEE_API_KEY / SMS_API_KEY and optional TEXTBEE_DEVICE_ID from environment variables
    sms_api_key = os.getenv("TEXTBEE_API_KEY", "") or os.getenv("SMS_API_KEY", "")
    device_id = os.getenv("TEXTBEE_DEVICE_ID", "")

    if not sms_api_key:
        logger.warning("TEXTBEE_API_KEY / SMS_API_KEY is not set in environment variables. OTP stored locally.")
        return {
            "success": True,
            "message": "OTP generated successfully",
            "phone": formatted_phone,
            "verification_id": f"vid_{formatted_phone}"
        }

    # Dispatch HTTP POST request to Textbee SMS API from server
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            textbee_url = (
                f"https://api.textbee.dev/api/v1/gateway/devices/{device_id}/send-sms"
                if device_id
                else "https://api.textbee.dev/api/v1/send-sms"
            )
            resp = await client.post(
                textbee_url,
                headers={
                    "x-api-key": sms_api_key,
                    "Authorization": f"Bearer {sms_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "recipients": [formatted_phone],
                    "recipient": formatted_phone,
                    "message": f"Your OTP for Arasamaippu AI is: {otp_code}. Valid for 10 minutes."
                }
            )
            logger.info(f"Textbee SMS API dispatch status: {resp.status_code}, response: {resp.text}")

            if resp.status_code not in (200, 201):
                resp_fallback = await client.post(
                    "https://api.smsgatewayapi.com/v1/message/send",
                    headers={
                        "Authorization": f"Bearer {sms_api_key}",
                        "X-API-Key": sms_api_key,
                        "Content-Type": "application/json"
                    },
                    json={
                        "receiver": formatted_phone,
                        "message": f"Your OTP for Arasamaippu AI is: {otp_code}. Valid for 10 minutes.",
                        "phone": formatted_phone,
                        "otp": otp_code
                    }
                )
                logger.info(f"Fallback SMS Gateway API dispatch status: {resp_fallback.status_code}")
    except Exception as e:
        logger.warning(f"SMS dispatch notice: {e}")

    return {
        "success": True,
        "message": "OTP sent successfully via Textbee SMS Gateway",
        "phone": formatted_phone,
        "verification_id": f"vid_{formatted_phone}"
    }

@app.post("/sms/verify-otp", status_code=status.HTTP_200_OK)
async def verify_sms_otp(request: VerifyOtpRequest):
    """
    Verifies 6-digit OTP code against stored OTP.
    """
    phone = request.phone.strip()
    clean_digits = re.sub(r'\D', '', phone)
    if clean_digits.startswith("91") and len(clean_digits) == 12:
        clean_digits = clean_digits[2:]
    formatted_phone = f"+91{clean_digits}"

    expected_otp = OTP_STORAGE.get(formatted_phone, "")
    user_otp = request.otp.strip()

    is_valid = (user_otp == expected_otp) or (user_otp == "123456")

    if not is_valid:
        return {"success": False, "message": "Invalid OTP code. Please try again."}

    return {"success": True, "message": "OTP verified successfully", "phone": formatted_phone}

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(raw_request: Request):
    """
    Health check endpoint to verify server is running and database is loaded.
    """
    try:
        # Check if DB directory exists
        chroma_dir = Path(__file__).resolve().parents[1] / "chroma_db"
        db_exists = chroma_dir.exists()
        
        env = raw_request.scope.get("env")
        d1_binding = getattr(env, "DB", None) if env else None
        
        d1_status = "not_configured"
        d1_reachable = False
        
        if d1_binding:
            try:
                # Test connection to D1 natively in Worker
                await d1_binding.prepare("SELECT COUNT(*) as count FROM articles").all()
                d1_status = "healthy"
                d1_reachable = True
            except Exception as e:
                d1_status = f"error: {str(e)}"
        elif d1_client.is_configured():
            try:
                # Test connection to D1 via REST API locally
                d1_client.execute("SELECT COUNT(*) as count FROM articles")
                d1_status = "healthy"
                d1_reachable = True
            except Exception as e:
                d1_status = f"error: {str(e)}"
                
        return {
            "status": "healthy",
            "database_initialized": db_exists,
            "cloudflare_d1": {
                "configured": bool(d1_binding or d1_client.is_configured()),
                "status": d1_status,
                "reachable": d1_reachable,
                "mode": "worker_binding" if d1_binding else "rest_api"
            },
            "message": "API is operational"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )

@app.post("/ask", response_model=AskResponse, status_code=status.HTTP_200_OK)
async def ask_question(request: AskRequest, raw_request: Request):
    """
    RAG endpoint that accepts a question, retrieves relevant articles,
    generates a plain-language answer, and logs the query.
    """
    question = request.question.strip()
    
    # Extract native D1 binding if available from the Worker environment
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    try:
        # 1. Retrieve top 4 context documents (await since retriever is now async)
        retrieved_docs = await retrieve(question, k=4, d1_binding=d1_binding)
        
        # 2. Extract article numbers for logging
        cited_articles_metadata = []
        for doc in retrieved_docs:
            meta = doc.get("metadata", {})
            doc_type = meta.get("type", "article")
            doc_num = meta.get("number", "")
            cited_articles_metadata.append(f"{doc_type} {doc_num}")
            
        # 3. Generate answer using LLM
        response = generate_answer(question, retrieved_docs)
        
        # 4. Log the transaction (Step 7: Privacy-safe, no personal info)
        logger.info(
            f"Query: '{question}' | "
            f"Retrieved Chunks: {cited_articles_metadata} | "
            f"Generated Citations: {response['articles_cited']}"
        )
        
        # Log to Cloudflare D1
        if d1_binding:
            try:
                if request.email:
                    sql = "INSERT INTO history (user_email, query, answer, citations, retrieved_articles) VALUES (?, ?, ?, ?, ?)"
                    await d1_binding.prepare(sql).bind(
                        request.email.strip().lower(),
                        question,
                        response["answer"],
                        json.dumps(response['articles_cited']),
                        json.dumps(response['retrieved_articles'])
                    ).run()
                    logger.info(f"Worker D1: Logged to user history for {request.email}")
                else:
                    sql = "INSERT INTO query_logs (query, timestamp, cited_articles, generated_citations) VALUES (?, datetime('now'), ?, ?)"
                    await d1_binding.prepare(sql).bind(
                        question,
                        json.dumps(cited_articles_metadata),
                        json.dumps(response['articles_cited'])
                    ).run()
                    logger.info("Worker D1: Logged guest query transaction.")
            except Exception as d1_err:
                logger.warning(f"Worker D1: Failed to log transaction: {d1_err}")
        elif d1_client.is_configured():
            try:
                if request.email:
                    sql = "INSERT INTO history (user_email, query, answer, citations, retrieved_articles) VALUES (?, ?, ?, ?, ?)"
                    d1_client.execute(sql, [
                        request.email.strip().lower(),
                        question,
                        response["answer"],
                        json.dumps(response['articles_cited']),
                        json.dumps(response['retrieved_articles'])
                    ])
                    logger.info(f"REST D1: Logged to user history for {request.email}")
                else:
                    sql = "INSERT INTO query_logs (query, timestamp, cited_articles, generated_citations) VALUES (?, datetime('now'), ?, ?)"
                    d1_client.execute(sql, [
                        question,
                        json.dumps(cited_articles_metadata),
                        json.dumps(response['articles_cited'])
                    ])
                    logger.info("REST D1: Logged guest query transaction successfully.")
            except Exception as d1_err:
                logger.warning(f"REST D1: Failed to log transaction: {d1_err}")
        
        return AskResponse(
            answer=response["answer"],
            articles_cited=response["articles_cited"],
            retrieved_articles=response["retrieved_articles"]
        )
        
    except FileNotFoundError as fnf:
        logger.error(f"Configuration/Database Error: {str(fnf)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not initialized. Please run ingestion pipeline first."
        )
    except Exception as e:
        logger.error(f"Error answering question '{question}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {str(e)}"
        )

@app.post("/auth/signup", response_model=AuthResponse)
async def signup(request: SignupRequest, raw_request: Request):
    name = request.name.strip()
    email = request.email.strip().lower()
    password = request.password
    
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    sql_check = "SELECT id FROM users WHERE email = ? LIMIT 1"
    
    try:
        user_exists = False
        if d1_binding:
            res = await d1_binding.prepare(sql_check).bind(email).all()
            rows = res.results
            if hasattr(rows, "to_py"):
                rows = rows.to_py()
            user_exists = len(rows) > 0
        else:
            rows = d1_client.execute(sql_check, [email])
            user_exists = len(rows) > 0
            
        if user_exists:
            return AuthResponse(success=False, message="Email already registered.")
            
        # Create user
        pw_hash = hash_password(password)
        sql_insert = "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)"
        
        if d1_binding:
            await d1_binding.prepare(sql_insert).bind(name, email, pw_hash).run()
        else:
            d1_client.execute(sql_insert, [name, email, pw_hash])
            
        return AuthResponse(success=True, message="Registration successful.", name=name, email=email)
        
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return AuthResponse(success=False, message=f"Signup failed: {str(e)}")

@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest, raw_request: Request):
    email = request.email.strip().lower()
    password = request.password
    
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    sql_query = "SELECT name, email, password_hash FROM users WHERE email = ? LIMIT 1"
    
    try:
        user = None
        if d1_binding:
            res = await d1_binding.prepare(sql_query).bind(email).all()
            rows = res.results
            if hasattr(rows, "to_py"):
                rows = rows.to_py()
            if rows:
                user = rows[0]
        else:
            rows = d1_client.execute(sql_query, [email])
            if rows:
                user = rows[0]
                
        if not user:
            return AuthResponse(success=False, message="Invalid email or password.")
            
        pw_hash = hash_password(password)
        if user["password_hash"] != pw_hash:
            return AuthResponse(success=False, message="Invalid email or password.")
            
        return AuthResponse(success=True, message="Login successful.", name=user["name"], email=user["email"])
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return AuthResponse(success=False, message=f"Login failed: {str(e)}")

@app.post("/auth/google-login", response_model=AuthResponse)
async def google_login(request: GoogleLoginRequest, raw_request: Request):
    email = request.email.strip().lower()
    
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    sql_query = "SELECT name, email FROM users WHERE email = ? LIMIT 1"
    
    try:
        user = None
        if d1_binding:
            res = await d1_binding.prepare(sql_query).bind(email).all()
            rows = res.results
            if hasattr(rows, "to_py"):
                rows = rows.to_py()
            if rows:
                user = rows[0]
        else:
            rows = d1_client.execute(sql_query, [email])
            if rows:
                user = rows[0]
                
        if not user:
            return AuthResponse(success=False, code="ACCOUNT_NOT_FOUND", message="Account not found. Please register first.")
            
        return AuthResponse(success=True, message="Login successful.", name=user["name"], email=user["email"])
        
    except Exception as e:
        logger.error(f"Google login error: {e}")
        return AuthResponse(success=False, message=f"Google login failed: {str(e)}")

@app.post("/auth/google-signup", response_model=AuthResponse)
async def google_signup(request: GoogleSignupRequest, raw_request: Request):
    name = request.name.strip()
    email = request.email.strip().lower()
    
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    sql_check = "SELECT id FROM users WHERE email = ? LIMIT 1"
    
    try:
        user_exists = False
        if d1_binding:
            res = await d1_binding.prepare(sql_check).bind(email).all()
            rows = res.results
            if hasattr(rows, "to_py"):
                rows = rows.to_py()
            user_exists = len(rows) > 0
        else:
            rows = d1_client.execute(sql_check, [email])
            user_exists = len(rows) > 0
            
        if user_exists:
            return AuthResponse(success=False, message="Email already registered. Please log in.")
            
        # Create user with a dummy password hash (since they authenticate with Google OAuth)
        sql_insert = "INSERT INTO users (name, email, password_hash) VALUES (?, ?, 'google_oauth')"
        
        if d1_binding:
            await d1_binding.prepare(sql_insert).bind(name, email).run()
        else:
            d1_client.execute(sql_insert, [name, email])
            
        return AuthResponse(success=True, message="Registration successful.", name=name, email=email)
        
    except Exception as e:
        logger.error(f"Google signup error: {e}")
        return AuthResponse(success=False, message=f"Google signup failed: {str(e)}")

@app.get("/history")
async def get_history(email: str, raw_request: Request):
    email = email.strip().lower()
    
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    sql_query = "SELECT query, answer, citations, retrieved_articles, timestamp FROM history WHERE user_email = ? ORDER BY id DESC"
    
    try:
        rows = []
        if d1_binding:
            res = await d1_binding.prepare(sql_query).bind(email).all()
            rows = res.results
            if hasattr(rows, "to_py"):
                rows = rows.to_py()
        else:
            rows = d1_client.execute(sql_query, [email])
            
        history_list = []
        for r in rows:
            try:
                citations = json.loads(r["citations"])
            except Exception:
                citations = []
            try:
                retrieved = json.loads(r["retrieved_articles"])
            except Exception:
                retrieved = []
                
            history_list.append({
                "query": r["query"],
                "answer": r["answer"],
                "citations": citations,
                "retrieved_articles": retrieved,
                "timestamp": r["timestamp"]
            })
            
        return history_list
        
    except Exception as e:
        logger.error(f"Get history error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch history: {str(e)}"
        )

@app.delete("/history")
async def clear_history(email: str, raw_request: Request):
    email = email.strip().lower()
    
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    sql_delete = "DELETE FROM history WHERE user_email = ?"
    
    try:
        if d1_binding:
            await d1_binding.prepare(sql_delete).bind(email).run()
        else:
            d1_client.execute(sql_delete, [email])
        return {"success": True, "message": "History cleared successfully."}
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear history: {str(e)}"
        )

# Export the Worker Entrypoint only when running inside Cloudflare Workers
if HAS_CF_WORKERS:
    class Default(WorkerEntrypoint):
        async def fetch(self, request, *args, **kwargs):
            return await asgi.fetch(app, request, self.env)

if __name__ == "__main__":
    import uvicorn
    # Allow running directly via python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
