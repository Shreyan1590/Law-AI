-- Schema for Cloudflare D1 SQL Database

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT UNIQUE,
    title TEXT,
    part TEXT,
    content TEXT,
    type TEXT
);

CREATE TABLE IF NOT EXISTS query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT,
    timestamp TEXT,
    cited_articles TEXT,
    generated_citations TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations TEXT NOT NULL,          -- JSON stringified array of citations
    retrieved_articles TEXT NOT NULL, -- JSON stringified array of article dicts
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
