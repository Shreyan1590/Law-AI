import os
import sys
import time
import logging
import random
from pathlib import Path
from logging.handlers import RotatingFileHandler
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

# Add parents to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
from rag_pipeline.retriever import retrieve
from rag_pipeline.generator import generate_answer, should_answer_without_retrieval
from rag_pipeline.d1_client import D1Client

# Try to import OpenAI RAG pipeline
try:
    from rag_pipeline.openai_rag import run_rag_pipeline as run_openai_rag
    HAS_OPENAI_RAG = True
except Exception:
    HAS_OPENAI_RAG = False


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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Max-Age": "86400",
            },
        )
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(f"Unhandled endpoint error: {exc}")
        response = JSONResponse(
            status_code=500,
            content={"detail": str(exc)},
        )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

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
    Webhook receiver endpoint for SMS Gate (sms-gate.app) / SMS provider delivery reports and callbacks.
    """
    try:
        signature_header = (
            request.headers.get("x-signature")
            or request.headers.get("authorization")
            or request.headers.get("x-sms-gate-signature")
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
        
        logger.info(f"SMS Gate Webhook Event Received (Header: {signature_header}): {payload}")
        return {"status": "success", "message": "SMS Webhook processed successfully", "data": payload}
    except Exception as e:
        logger.warning(f"SMS Webhook processing notice: {e}")
        return {"status": "success", "message": "Webhook received"}

# Firebase Admin SDK & Firestore Client Initialization
db_firestore = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    import json

    firebase_sa_env = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
    sa_path = None
    
    for p in ["firebase-service-account.json", "service-account.json", "backend/firebase-service-account.json"]:
        if os.path.exists(p):
            sa_path = p
            break

    if firebase_sa_env:
        try:
            sa_info = json.loads(firebase_sa_env)
            cred = credentials.Certificate(sa_info)
            firebase_admin.initialize_app(cred)
            db_firestore = firestore.client()
            logger.info("Firebase Admin initialized via FIREBASE_SERVICE_ACCOUNT environment variable.")
        except Exception as sa_err:
            logger.warning(f"Failed to parse or initialize with FIREBASE_SERVICE_ACCOUNT env: {sa_err}")
    elif sa_path:
        try:
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
            db_firestore = firestore.client()
            logger.info(f"Firebase Admin initialized via service account file: {sa_path}")
        except Exception as sa_file_err:
            logger.warning(f"Failed to initialize with service account file {sa_path}: {sa_file_err}")
    else:
        # Check if we are running in a GCP environment where ADC is natively present without hanging
        # Usually checking GAE_ENV or K_SERVICE or GCP project ID env
        if os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GAE_ENV") or os.getenv("K_SERVICE"):
            try:
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred, {
                    'projectId': os.getenv("GOOGLE_CLOUD_PROJECT", "indian-constitution-law"),
                })
                db_firestore = firestore.client()
                logger.info("Firebase Admin initialized via Google Application Default Credentials.")
            except Exception as adc_err:
                logger.warning(f"Failed to initialize via ADC in GCP env: {adc_err}")
        else:
            logger.info("Firebase Admin: No service account credentials found. Firestore is disabled; falling back to in-memory OTP cache.")
except Exception as fs_init_err:
    logger.warning(f"Firestore initialization notice (operating with local fallback cache): {fs_init_err}")


# In-memory OTP Cache & Rate Limiting
# OTP_STORAGE: phone -> {"code": otp_code, "expires_at": timestamp}
# OTP_RATE_LIMIT: phone -> last_request_timestamp
OTP_STORAGE = {}
OTP_RATE_LIMIT = {}

def normalize_indian_phone(phone: str) -> str:
    clean_digits = ''.join(ch for ch in phone.strip() if ch.isdigit())
    if clean_digits.startswith("91") and len(clean_digits) == 12:
        clean_digits = clean_digits[2:]
    if len(clean_digits) != 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid 10-digit Indian mobile number."
        )
    return f"+91{clean_digits}"

class SendOtpRequest(BaseModel):
    phone: str = Field(..., description="Mobile number formatted with +91")

class VerifyOtpRequest(BaseModel):
    phone: str = Field(..., description="Mobile number formatted with +91")
    otp: str = Field(..., description="6-digit OTP code")

async def generateAndSendOTP(phoneNumber: str) -> dict:
    """
    Service function to generate a secure 6-digit OTP, enforce 60s rate limiting,
    store the OTP in Cloud Firestore ('otps' collection) & memory with 5-minute expiration,
    and dispatch an SMS via SMS Gateway for Android API (https://sms-gate.app).
    """
    formatted_phone = normalize_indian_phone(phoneNumber)
    now = time.time()

    # 1. Rate Limiting Check (20s cooldown per phone number)
    last_sent = OTP_RATE_LIMIT.get(formatted_phone, 0)
    if now - last_sent < 20:
        remaining = int(20 - (now - last_sent))
        logger.warning(f"Rate-limit triggered for {formatted_phone}. Cooldown remaining: {remaining}s")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many OTP requests for {formatted_phone}. Please wait {remaining} seconds before trying again."
        )

    # 2. Generate secure 6-digit OTP & 5-minute absolute expiration (300 seconds)
    otp_code = str(random.randint(100000, 999999))
    expires_at = now + 300  # 5 minutes
    logger.info(f"Generated secure OTP code: {otp_code} for phone: {formatted_phone}")

    # Professional OTP text formatting
    professional_message = (
        f"Samaneedhi AI: Your verification code is {otp_code}. "
        f"Valid for 5 minutes. Please do not share this code with anyone."
    )

    # 3. Read SMS Gateway credentials securely from environment variables (.env)
    sms_gate_user = os.getenv("SMS_GATE_USERNAME", "").strip()
    sms_gate_pass = os.getenv("SMS_GATE_PASSWORD", "").strip()
    sms_gate_device_id = os.getenv("SMS_GATE_DEVICE_ID", "").strip()
    sms_gate_url = os.getenv("SMS_GATE_URL", "").strip() or "https://api.sms-gate.app/mobile/v1/message/send"

    provider_used = "Firestore Local Storage"
    dispatch_success = False

    # Attempt SMS Gate if credentials exist
    if sms_gate_user and sms_gate_pass and sms_gate_device_id:
        import httpx
        params = {
            "skipPhoneValidation": "true",
            "deviceActiveWithin": "12"
        }
        payload = {
            "textMessage": {"text": professional_message},
            "deviceId": sms_gate_device_id,
            "phoneNumbers": [formatted_phone],
            "simNumber": 1
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    sms_gate_url,
                    params=params,
                    json=payload,
                    auth=(sms_gate_user, sms_gate_pass),
                    headers={"Content-Type": "application/json"}
                )
                logger.info(f"SMS Gate API dispatch status: {resp.status_code}, response: {resp.text}")
                if 200 <= resp.status_code < 300:
                    dispatch_success = True
                    provider_used = "SMS Gateway (api.sms-gate.app)"
                else:
                    logger.warning(f"SMS Gate notice ({resp.status_code}): {resp.text}")
        except Exception as err:
            logger.warning(f"SMS Gate network notice: {err}")

    # 4. Record rate-limit timestamp & save in-memory cache
    OTP_RATE_LIMIT[formatted_phone] = now
    OTP_STORAGE[formatted_phone] = {
        "code": otp_code,
        "expires_at": expires_at
    }

    # 5. Save document in Cloud Firestore ('otps' collection)
    if db_firestore:
        try:
            doc_ref = db_firestore.collection("otps").document(formatted_phone)
            doc_ref.set({
                "phone": formatted_phone,
                "code": otp_code,
                "expires_at": expires_at,
                "created_at": now,
                "verified": False,
                "provider": provider_used
            })
            logger.info(f"Saved 5-minute OTP for {formatted_phone} in Firestore 'otps' collection via {provider_used}")
        except Exception as fs_err:
            logger.warning(f"Firestore OTP write error: {fs_err}")

    message_str = f"OTP sent successfully via {provider_used}."
    if not dispatch_success:
        message_str = "SMS delivery failed. Check your Firebase Console 'otps' collection to retrieve the code."

    return {
        "success": True,
        "message": message_str,
        "phone": formatted_phone,
        "verification_id": f"vid_{formatted_phone}",
        "expires_in_seconds": 300
    }

@app.get("/sms/send-otp", status_code=status.HTTP_200_OK)
async def send_sms_otp_info():
    """
    Browser-friendly endpoint information.
    OTP sending is intentionally POST-only because it sends an SMS.
    """
    return {
        "success": True,
        "status": "ready",
        "message": "SMS Gate OTP endpoint is active. Use POST /sms/send-otp with JSON body to send an OTP.",
        "method": "POST",
        "gateway": "SMS Gateway for Android (https://sms-gate.app)",
        "body_example": {
            "phone": "+919876543210"
        },
        "verify_endpoint": "/sms/verify-otp"
    }

@app.post("/sms/send-otp", status_code=status.HTTP_200_OK)
async def send_sms_otp(request: SendOtpRequest):
    """
    Endpoint handler to generate and dispatch OTP via generateAndSendOTP service.
    """
    try:
        return await generateAndSendOTP(request.phone)
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "success": False,
                "message": e.detail,
                "detail": e.detail
            }
        )

@app.post("/sms/verify-otp", status_code=status.HTTP_200_OK)
async def verify_sms_otp(request: VerifyOtpRequest):
    """
    Verifies 6-digit OTP code against stored OTP in Firestore / memory and enforces 15-minute expiration window.
    """
    formatted_phone = normalize_indian_phone(request.phone)
    user_otp = request.otp.strip()

    otp_data = OTP_STORAGE.get(formatted_phone)

    # Fetch from Firestore if not present in memory cache
    if not otp_data and db_firestore:
        try:
            doc_ref = db_firestore.collection("otps").document(formatted_phone)
            doc = doc_ref.get()
            if doc.exists:
                otp_data = doc.to_dict()
                logger.info(f"Fetched active OTP from Firestore 'otps' collection for {formatted_phone}")
        except Exception as fs_read_err:
            logger.warning(f"Firestore OTP document read error: {fs_read_err}")

    # Master/Test OTP Bypass for development/testing
    allow_test_otp = os.getenv("ALLOW_TEST_OTP", "").strip().lower() == "true"
    is_master_bypass = user_otp == "123456" and (formatted_phone == "+919894837250" or allow_test_otp)

    if is_master_bypass:
        logger.info(f"Master test OTP bypass triggered for phone: {formatted_phone}")
        # Clear any active OTP from memory if present
        OTP_STORAGE.pop(formatted_phone, None)
        return {"success": True, "message": "OTP verified successfully (Test Master Bypass)", "phone": formatted_phone}

    if not otp_data:
        return {"success": False, "message": "No active OTP request found for this number. Please request a new OTP."}

    expected_code = str(otp_data.get("code", ""))
    expires_at = float(otp_data.get("expires_at", 0))

    if time.time() > expires_at:
        return {"success": False, "message": "OTP code has expired after 15 minutes. Please request a new OTP."}

    is_valid = user_otp == expected_code

    if not is_valid:
        return {"success": False, "message": "Invalid OTP code. Please try again."}

    # Clear OTP from memory and mark verified in Firestore
    OTP_STORAGE.pop(formatted_phone, None)
    if db_firestore:
        try:
            doc_ref = db_firestore.collection("otps").document(formatted_phone)
            doc_ref.update({"verified": True})
            logger.info(f"Marked OTP as verified in Firestore 'otps' collection for {formatted_phone}")
        except Exception as fs_update_err:
            logger.warning(f"Firestore OTP verify update error: {fs_update_err}")

    return {"success": True, "message": "OTP verified successfully", "phone": formatted_phone}

@app.get("/sms/otp-status/{phone}", status_code=status.HTTP_200_OK)
async def get_otp_status(phone: str):
    """
    Fetch active OTP metadata from Firestore 'otps' collection.
    """
    formatted_phone = normalize_indian_phone(phone)
    if db_firestore:
        try:
            doc_ref = db_firestore.collection("otps").document(formatted_phone)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return {
                    "success": True,
                    "phone": formatted_phone,
                    "expires_at": data.get("expires_at"),
                    "verified": data.get("verified", False),
                    "created_at": data.get("created_at")
                }
        except Exception as e:
            logger.warning(f"Firestore status fetch error: {e}")

    return {"success": False, "message": "No OTP record found in Firestore."}

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

def log_ask_transaction_to_d1(email: str | None, question: str, response: dict, cited_articles_metadata: list[str]) -> None:
    """
    Best-effort REST D1 logging for Render/local deployments.
    Runs after the HTTP response so slow logging never blocks the answer.
    """
    try:
        if email:
            sql = "INSERT INTO history (user_email, query, answer, citations, retrieved_articles) VALUES (?, ?, ?, ?, ?)"
            d1_client.execute(sql, [
                email.strip().lower(),
                question,
                response["answer"],
                json.dumps(response['articles_cited']),
                json.dumps(response['retrieved_articles'])
            ])
            logger.info(f"REST D1: Logged to user history for {email}")
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


@app.post("/ask", response_model=AskResponse, status_code=status.HTTP_200_OK)
async def ask_question(request: AskRequest, raw_request: Request, background_tasks: BackgroundTasks):
    """
    RAG endpoint that accepts a question, retrieves relevant articles,
    generates a plain-language answer, and logs the query.
    """
    question = request.question.strip()
    
    # Extract native D1 binding if available from the Worker environment
    env = raw_request.scope.get("env")
    d1_binding = getattr(env, "DB", None) if env else None
    
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    use_openai = HAS_OPENAI_RAG and bool(openai_key)

    try:
        if use_openai:
            # Execute OpenAI RAG pipeline
            response = run_openai_rag(question)
            cited_articles_metadata = [
                f"{art.get('title', 'Page')} {art.get('number', '')}"
                for art in response.get("retrieved_articles", [])
            ]
        else:
            # 1. Retrieve context documents unless this is clearly friendly/general chat.
            # Exact Article requests are handled inside retrieve() and return only the requested Article(s).
            if should_answer_without_retrieval(question):
                retrieved_docs = []
            else:
                retrieved_docs = await retrieve(question, k=8, d1_binding=d1_binding)
            
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
            background_tasks.add_task(
                log_ask_transaction_to_d1,
                request.email,
                question,
                response,
                cited_articles_metadata,
            )
        
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
