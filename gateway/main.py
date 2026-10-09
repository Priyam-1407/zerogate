import asyncio
import base64
import hmac
import itertools
import sqlite3
import time

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect

from gateway.policy import check_access, load_policy

SECRET = "zerogate-dev-secret-key-change-me-0123456789"
CONNECTOR_SECRET = "connector-dev-secret-change-me"
ALGO = "HS256"

policy = load_policy()
app = FastAPI()

connectors = {}   # connector_id -> websocket
pending = {}      # request_id -> future
_ids = itertools.count(1)

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


@app.websocket("/_connector/ws")
async def connector_ws(ws: WebSocket):
    cid = ws.headers.get("x-connector-id", "")
    secret = ws.headers.get("x-connector-secret", "")
    if not cid or not hmac.compare_digest(secret, CONNECTOR_SECRET):
        await ws.close(code=1008)
        return
    await ws.accept()
    connectors[cid] = ws
    print(f"connector online: {cid}")
    try:
        while True:
            msg = await ws.receive_json()
            fut = pending.pop(msg["id"], None)
            if fut and not fut.done():
                fut.set_result(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if connectors.get(cid) is ws:
            del connectors[cid]
        print(f"connector offline: {cid}")


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

    res = policy["resources"][resource]
    body = await request.body()

    # Tunnel mode: request connector ke through jaati hai
    if "connector" in res:
        ws = connectors.get(res["connector"])
        if ws is None:
            raise HTTPException(502, "connector offline (fail closed)")
        req_id = str(next(_ids))
        fut = asyncio.get_running_loop().create_future()
        pending[req_id] = fut
        await ws.send_json({
            "id": req_id,
            "method": request.method,
            "path": path,
            "query": request.url.query,
            "body": base64.b64encode(body).decode(),
        })
        try:
            msg = await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            pending.pop(req_id, None)
            raise HTTPException(504, "connector timeout")
        return Response(
            content=base64.b64decode(msg["body"]),
            status_code=msg["status"],
            media_type=msg.get("content_type"),
        )

    # Direct mode (purana tareeka)
    async with httpx.AsyncClient() as client:
        r = await client.request(request.method, f"{res['upstream']}/{path}", content=body)
    return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))