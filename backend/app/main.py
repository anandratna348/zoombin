
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# Store meeting data in the current user's home directory.
DATA_DIR = Path.home() / ".zoombin"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "zoombin.sqlite3"

app = FastAPI(
    title="Zoombin API",
    description="Local API for the Zoombin meeting assistant.",
    version="0.1.0",
)

# Development origins for the future Tauri + React interface.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with get_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ended_at TEXT
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                speaker TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id)
                    REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_transcripts_session
            ON transcripts(session_id, id);
            """
        )


@app.on_event("startup")
def startup():
    initialize_database()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_session_or_404(db, session_id: str):
    session = db.execute(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


class CreateSession(BaseModel):
    title: str = Field(default="New Meeting", min_length=1, max_length=200)


class AddTranscript(BaseModel):
    speaker: str = Field(default="Unknown", min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20000)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Zoombin",
        "database": "SQLite",
    }


@app.post("/api/sessions", status_code=201)
def create_session(payload: CreateSession):
    session_id = str(uuid.uuid4())
    created_at = utc_now()

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO sessions (id, title, created_at)
            VALUES (?, ?, ?)
            """,
            (session_id, payload.title.strip(), created_at),
        )

    return {
        "id": session_id,
        "title": payload.title.strip(),
        "created_at": created_at,
        "ended_at": None,
    }


@app.get("/api/sessions")
def list_sessions():
    with get_connection() as db:
        sessions = db.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()

    return [dict(session) for session in sessions]


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    with get_connection() as db:
        session = get_session_or_404(db, session_id)

        transcripts = db.execute(
            """
            SELECT id, speaker, text, timestamp
            FROM transcripts
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    return {
        **dict(session),
        "transcripts": [dict(row) for row in transcripts],
    }


@app.post("/api/sessions/{session_id}/transcript", status_code=201)
def add_transcript(session_id: str, payload: AddTranscript):
    with get_connection() as db:
        session = get_session_or_404(db, session_id)

        if session["ended_at"] is not None:
            raise HTTPException(
                status_code=409,
                detail="Cannot add transcript to an ended session",
            )

        timestamp = utc_now()
        cursor = db.execute(
            """
            INSERT INTO transcripts
                (session_id, speaker, text, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                session_id,
                payload.speaker.strip(),
                payload.text.strip(),
                timestamp,
            ),
        )

        transcript_id = cursor.lastrowid

    return {
        "id": transcript_id,
        "session_id": session_id,
        "speaker": payload.speaker.strip(),
        "text": payload.text.strip(),
        "timestamp": timestamp,
    }


@app.patch("/api/sessions/{session_id}/end")
def end_session(session_id: str):
    with get_connection() as db:
        session = get_session_or_404(db, session_id)

        if session["ended_at"] is None:
            db.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (utc_now(), session_id),
            )

        updated = get_session_or_404(db, session_id)

    return dict(updated)


@app.get("/api/sessions/{session_id}/export")
def export_session(
    session_id: str,
    format: Literal["json", "txt", "markdown"] = "markdown",
):
    with get_connection() as db:
        session = get_session_or_404(db, session_id)
        rows = db.execute(
            """
            SELECT speaker, text, timestamp
            FROM transcripts
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    data = {
        **dict(session),
        "transcripts": [dict(row) for row in rows],
    }

    if format == "json":
        return data

    if format == "txt":
        content = "\n".join(
            f'{row["speaker"]}: {row["text"]}' for row in rows
        )
        return {"filename": "zoombin-transcript.txt", "content": content}

    lines = [
        f'# {session["title"]}',
        "",
        f'Created: {session["created_at"]}',
        "",
    ]
    lines.extend(
        f'**{row["speaker"]}:** {row["text"]}'
        for row in rows
    )

    return {
        "filename": "zoombin-transcript.md",
        "content": "\n\n".join(lines),
    }
