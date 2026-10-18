
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .auth import create_access_token, get_current_user, hash_password
from .google_auth import verify_google_id_token


DATA_DIR = Path.home() / ".zoombin"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "zoombin.sqlite3"

app = FastAPI(
    title="Zoombin API",
    description="Local meeting assistant with Google authentication",
    version="0.2.0",
)

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
    allow_headers=["Authorization", "Content-Type"],
)

bearer_scheme = HTTPBearer(auto_error=False)


# -------------------- DATABASE --------------------

def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def initialize_database():
    with get_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                user_id TEXT REFERENCES users(id)
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

        # Migrate an existing database without deleting meetings.
        session_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(sessions)")
        }

        if "user_id" not in session_columns:
            db.execute(
                "ALTER TABLE sessions ADD COLUMN user_id TEXT REFERENCES users(id)"
            )

        user_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(users)")
        }

        if "google_sub" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")

        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
            ON users(google_sub)
            WHERE google_sub IS NOT NULL
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON sessions(user_id, created_at)
            """
        )


@app.on_event("startup")
def startup():
    initialize_database()


# -------------------- REQUEST SCHEMAS --------------------

class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=10000)


class CreateSession(BaseModel):
    title: str = Field(default="New Meeting", min_length=1, max_length=200)


class AddTranscript(BaseModel):
    speaker: str = Field(default="Unknown", min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20000)


# -------------------- AUTHENTICATION --------------------

@app.post("/api/auth/google")
def google_login(payload: GoogleLoginRequest):
    """
    Accept a Google ID token, verify it, and issue a Zoombin JWT.

    The Google ID token must have been issued for the configured
    GOOGLE_CLIENT_ID.
    """
    profile = verify_google_id_token(payload.id_token)

    google_sub = profile["google_sub"]
    email = profile["email"].strip().lower()
    name = profile["name"].strip() or "Zoombin user"

    with get_connection() as db:
        user = db.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE google_sub = ?
            """,
            (google_sub,),
        ).fetchone()

        if user is None:
            # Do not automatically link a pre-existing password account
            # just because its email matches.
            existing = db.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()

            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "An account already exists for this email. "
                        "Use an explicit account-linking process."
                    ),
                )

            user_id = str(uuid.uuid4())
            created_at = utc_now()

            # Existing schema requires password_hash. This random hash
            # is never exposed and cannot be used as a known password.
            unusable_password_hash = hash_password(
                secrets.token_urlsafe(48)
            )

            db.execute(
                """
                INSERT INTO users
                    (id, name, email, password_hash, created_at, google_sub)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    name,
                    email,
                    unusable_password_hash,
                    created_at,
                    google_sub,
                ),
            )

            user = {
                "id": user_id,
                "name": name,
                "email": email,
            }
        else:
            user = dict(user)

    return {
        "access_token": create_access_token(user["id"]),
        "token_type": "bearer",
        "expires_in": 1800,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
        },
    }


@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return user


# -------------------- SESSION HELPERS --------------------

def get_owned_session(db, session_id: str, user_id: str):
    session = db.execute(
        """
        SELECT *
        FROM sessions
        WHERE id = ? AND user_id = ?
        """,
        (session_id, user_id),
    ).fetchone()

    if session is None:
        # Do not disclose another user's session existence.
        raise HTTPException(status_code=404, detail="Session not found")

    return session


# -------------------- HEALTH --------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Zoombin",
        "database": "SQLite",
    }


# -------------------- MEETINGS --------------------

@app.post("/api/sessions", status_code=201)
def create_session(
    payload: CreateSession,
    user: dict = Depends(get_current_user),
):
    title = payload.title.strip()

    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be blank")

    session_id = str(uuid.uuid4())
    created_at = utc_now()

    with get_connection() as db:
        db.execute(
            """
            INSERT INTO sessions (id, title, created_at, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, title, created_at, user["id"]),
        )

    return {
        "id": session_id,
        "title": title,
        "created_at": created_at,
        "ended_at": None,
    }


@app.get("/api/sessions")
def list_sessions(user: dict = Depends(get_current_user)):
    with get_connection() as db:
        sessions = db.execute(
            """
            SELECT id, title, created_at, ended_at
            FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user["id"],),
        ).fetchall()

    return [dict(session) for session in sessions]


@app.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    with get_connection() as db:
        session = get_owned_session(db, session_id, user["id"])

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
def add_transcript(
    session_id: str,
    payload: AddTranscript,
    user: dict = Depends(get_current_user),
):
    speaker = payload.speaker.strip()
    text = payload.text.strip()

    if not speaker or not text:
        raise HTTPException(
            status_code=422,
            detail="Speaker and transcript text cannot be blank",
        )

    with get_connection() as db:
        session = get_owned_session(db, session_id, user["id"])

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
            (session_id, speaker, text, timestamp),
        )

        transcript_id = cursor.lastrowid

    return {
        "id": transcript_id,
        "session_id": session_id,
        "speaker": speaker,
        "text": text,
        "timestamp": timestamp,
    }


@app.patch("/api/sessions/{session_id}/end")
def end_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    with get_connection() as db:
        session = get_owned_session(db, session_id, user["id"])

        if session["ended_at"] is None:
            db.execute(
                """
                UPDATE sessions
                SET ended_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (utc_now(), session_id, user["id"]),
            )

        updated = get_owned_session(db, session_id, user["id"])

    return dict(updated)


@app.get("/api/sessions/{session_id}/export")
def export_session(
    session_id: str,
    format: Literal["json", "txt", "markdown"] = "markdown",
    user: dict = Depends(get_current_user),
):
    with get_connection() as db:
        session = get_owned_session(db, session_id, user["id"])

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
            f'{row["speaker"]}: {row["text"]}'
            for row in rows
        )
        return {
            "filename": "zoombin-transcript.txt",
            "content": content,
        }

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
