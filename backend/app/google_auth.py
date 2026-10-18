
import os

from fastapi import HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests
from google.oauth2 import id_token


def verify_google_id_token(token: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")

    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="Google authentication is not configured.",
        )

    if not token or len(token) > 10000:
        raise HTTPException(status_code=401, detail="Invalid Google token.")

    try:
        claims = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            audience=client_id,
        )
    except (ValueError, GoogleAuthError):
        raise HTTPException(
            status_code=401,
            detail="Google token is invalid or expired.",
        )

    if claims.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise HTTPException(status_code=401, detail="Invalid token issuer.")

    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=401,
            detail="A verified Google email is required.",
        )

    if not claims.get("sub") or not claims.get("email"):
        raise HTTPException(
            status_code=401,
            detail="Google token is missing identity information.",
        )

    return {
        "google_sub": claims["sub"],
        "email": claims["email"].lower(),
        "name": claims.get("name") or "Zoombin user",
        "picture": claims.get("picture"),
    }
