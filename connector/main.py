import asyncio
import base64
import json

import httpx
from websockets.asyncio.client import connect

GATEWAY_WS = "ws://127.0.0.1:8000/_connector/ws"
CONNECTOR_ID = "hr-connector"
CONNECTOR_SECRET = "connector-dev-secret-change-me"
LOCAL_APP = "http://127.0.0.1:9000"

tasks = set()


async def handle(ws, client, msg):
    url = f"{LOCAL_APP}/{msg['path']}"
    if msg.get("query"):
        url += "?" + msg["query"]
    try:
        r = await client.request(msg["method"], url, content=base64.b64decode(msg["body"]))
        out = {
            "id": msg["id"],
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "body": base64.b64encode(r.content).decode(),
        }
    except Exception as e:
        out = {
            "id": msg["id"],
            "status": 502,
            "content_type": "text/plain",
            "body": base64.b64encode(f"connector error: {e}".encode()).decode(),
        }
    await ws.send(json.dumps(out))


async def main():
    headers = {"x-connector-id": CONNECTOR_ID, "x-connector-secret": CONNECTOR_SECRET}
    while True:
        try:
            async with connect(GATEWAY_WS, additional_headers=headers) as ws:
                print("connected to gateway (outbound)")
                async with httpx.AsyncClient() as client:
                    async for raw in ws:
                        t = asyncio.create_task(handle(ws, client, json.loads(raw)))
                        tasks.add(t)
                        t.add_done_callback(tasks.discard)
        except Exception as e:
            print("disconnected, retrying in 2s:", e)
            await asyncio.sleep(2)


asyncio.run(main())