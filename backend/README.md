# Indian Constitution Legal Assistant — Backend

This is the backend RAG pipeline and FastAPI server for the Indian Constitution Legal Assistant. It uses FastAPI for the API, ChromaDB as a vector store, HuggingFace embeddings (`all-MiniLM-L6-v2`) for local retrieval, and Google's Gemini API for answer generation.

---

## Technical Prerequisites

Ensure you have **Python 3.10+** installed on your system.

---

## Local Setup & Development

### 1. Configure Environment Variables
Create a file named `.env` in the `backend/` directory:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
D1_REQUEST_TIMEOUT_SECONDS=8
TEXTBEE_API_KEY=your_textbee_api_key_here
TEXTBEE_DEVICE_ID=your_textbee_device_id_here
```
> Get a free API key from [Google AI Studio](https://aistudio.google.com/).
> For OTP SMS, connect an Android phone in Textbee and use the device-specific API key/device ID.

### 2. Ingest the Constitutional Data
Run the data ingestion script to download the official Constitution text, parse it into articles, generate embeddings, and build the local vector database:
```bash
# Make sure you are in the f:\Law AI\backend directory
.venv\Scripts\python.exe data_ingestion\ingest.py
```
*At the end, you should see a message like: "Loaded 395+ Articles, 12 Schedules, X chunks total. Chroma DB saved successfully."*

### 3. Test Retrieval Standalone (Optional)
You can verify similarity search is working:
```bash
.venv\Scripts\python.exe rag_pipeline\retriever.py "What is article 21?"
```

### 4. Run the FastAPI Server Locally
Start the server in reload/development mode:
```bash
.venv\Scripts\python.exe api\main.py
```
The server will start at **`http://localhost:8000`**.

### 5. Interactive Testing
- Visit **`http://localhost:8000/docs`** in your web browser. This opens the auto-generated Swagger UI.
- Click on the `/ask` endpoint, click **"Try it out"**, enter a question like `{"question": "What is the right to equality?"}`, and hit **Execute**.
- Alternatively, test using `curl` in your terminal:
  ```bash
  curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"What is article 21?\"}"
  ```

---

## Production Deployment (Render)

To deploy the backend to Render's free tier so the mobile app can reach it over the internet:

### Step 1: Push to GitHub
1. Create a new public or private repository on GitHub (e.g. `indian-constitution-rag`).
2. Initialize git in your project directory, commit the backend files (do **NOT** commit `.env` or `chroma_db/`), and push to GitHub:
   ```bash
   git init
   git add requirements.txt api/ data_ingestion/ rag_pipeline/ README.md
   git commit -m "Initial commit of FastAPI backend"
   git remote add origin <your-github-repo-url>
   git branch -M main
   git push -u origin main
   ```

### Step 2: Set up Render
1. Sign up on [Render.com](https://render.com) using your GitHub account.
2. Click **New +** and select **Web Service**.
3. Connect your newly created GitHub repository.

### Step 3: Configure the Web Service
Configure the web service details:
- **Name:** `constitution-legal-assistant`
- **Region:** Choose a region close to your target users (e.g., `Singapore` is closest to India)
- **Branch:** `main`
- **Runtime:** `Python 3`
- **Build Command:** `pip install -r requirements.txt && python data_ingestion/ingest.py`
  *(This installs dependencies and builds the vector database on Render automatically during deploy!)*
- **Start Command:** `uvicorn api.main:app --host 0.0.0.0 --port 10000`
- **Plan Type:** `Free`

### Step 4: Add Environment Variables
1. Scroll down to the **Environment Variables** section (or click the **Environment** tab).
2. Click **Add Environment Variable**.
3. Set Key to `GOOGLE_API_KEY` and Value to your actual Gemini API key.
4. Add `TEXTBEE_API_KEY` and `TEXTBEE_DEVICE_ID` from your Textbee dashboard so `/sms/send-otp` can dispatch OTP messages.
5. Keep `GEMINI_MODEL=gemini-2.5-flash` and `D1_REQUEST_TIMEOUT_SECONDS=8` unless you intentionally want a different model or timeout.
6. Click **Create Web Service**.

### Step 5: Accessing Your Public API URL
- Once deployment succeeds, Render provides your public URL at the top of the dashboard (e.g. `https://constitution-legal-assistant.onrender.com`).
- Your endpoints will be reachable at:
  - Health check: `https://constitution-legal-assistant.onrender.com/health`
  - Ask: `https://constitution-legal-assistant.onrender.com/ask`

---

## ⚠️ Important Free-Tier Flags

- **Cold Starts:** On Render's Free tier, the server spins down after 15 minutes of inactivity. When the mobile app makes a request after it has slept, the server takes **30 to 60 seconds** to boot back up. The app has been designed to show a loading indicator and handle timeouts gracefully.
- **Gemini Free Limits:** Google AI Studio free tier limits you to ~15 Requests Per Minute (RPM). If you exceed this, you'll receive rate-limit errors.
