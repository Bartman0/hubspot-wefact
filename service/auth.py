import os
from typing import Optional

from fastapi import Header, HTTPException

VALID_API_KEY = os.environ["API_KEY"]


def verify_api_key(authorization: Optional[str] = Header(None)):
    """
    Checks if the Bearer token matches our expected key.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Expecting format: "Bearer sk-..."
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer" or token != VALID_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API key")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid authorization header format"
        )

    return token
