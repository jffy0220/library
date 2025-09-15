import os
from datetime import datetime, date
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

DB_CFG = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "snippets_db"),
    user=os.getenv("DB_USER", "snip_user"),
    password=os.getenv("DB_PASSWORD", "snip_pass"),
)

def get_conn():
    return psycopg2.connect(**DB_CFG)

class SnippetIn(BaseModel):
    date_read: Optional[date] = None
    book_name: Optional[str] = None
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    text_snippet: Optional[str] = None
    thoughts: Optional[str] = None
    created_by: Optional[str] = None

class SnippetOut(SnippetIn):
    id: int
    created_utc: datetime


app = FastAPI(title="Book Snippets API (no auth)")

# Vite proxy origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/snippets", response_model=List[SnippetOut])
def list_snippets():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, created_utc, date_read, book_name, page_number, chapter, verse, text_snippet, thoughts, created_by
            FROM snippets
            ORDER BY id DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
    return [SnippetOut(**dict(r)) for r in rows]

#test

@app.post("/api/snippets", status_code=201)
def create_snippet(payload: SnippetIn):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO snippets (date_read, book_name, page_number, chapter, verse, text_snippet, thoughts, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (payload.date_read, payload.book_name, payload.page_number, payload.chapter,
              payload.verse, payload.text_snippet, payload.thoughts, payload.created_by))
        new_id = cur.fetchone()[0]
        conn.commit()
    return {"id": new_id}

@app.get("/api/snippets/{sid}", response_model=SnippetOut)
def get_snippet(sid: int):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM snippets WHERE id=%s", (sid,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return SnippetOut(**dict(row))

# run: uvicorn main:app --host 127.0.0.1 --port 8000 --reload
