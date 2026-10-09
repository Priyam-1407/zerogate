import sqlite3
import time

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response

from gateway.policy import check_access, load_policy

SECRET = "zerogate-dev-secret-key-change-me-0123456789"
ALGO = "HS256"

policy = load_policy()
app = FastAPI()

db = sqlite3.connect("audit.db", check_same_thread=False)
db.execute(
    "CREATE TABLE IF NOT EXISTS audit "
    "(ts REAL, user TEXT, role TEXT, resource TEXT, path TEXT, decision TEXT, reason TEXT)"
)
db.commit()


def log(user, role, resource, path, decision, reason):
    db.execute(
        "INSERT INTO audit VALUES (?,?,?,?,?,?,?)",
        (time.time(), user, role, resource, path, decision, reason),
    )
    db.commit()


@app.api_route("/{resource}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(resource: str, path: str, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        log("-", "-", resource, path, "DENY", "missing token")
        raise HTTPException(401, "missing token")

    try:
        claims = jwt.decode(auth[7:], SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        log("-", "-", resource, path, "DENY", "invalid token")
        raise HTTPException(401, "invalid token")

    user = claims.get("sub", "-")
    role = claims.get("role", "-")

    allowed, reason = check_access(policy, role, resource)
    log(user, role, resource, path, "ALLOW" if allowed else "DENY", reason)
    if not allowed:
        raise HTTPException(403, reason)

    upstream = policy["resources"][resource]["upstream"]
    async with httpx.AsyncClient() as client:
        r = await client.request(request.method, f"{upstream}/{path}", content=await request.body())
    return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))