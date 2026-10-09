# ZeroGate

A mini **zero-trust access gateway** (ZTNA prototype). Every request is authenticated, authorized against a policy (default deny), logged, and forwarded to a private app through an **outbound-only connector tunnel**.

> Functional prototype built in 3 days. Not production-ready (see Limitations).

## Architecture

```
User (JWT) -> Gateway :8000 -> [WebSocket tunnel] -> Connector -> Private app :9000
                  |                      ^
                  v                      |
             audit.db        connector dials OUT to the gateway
```

1. **Gateway** verifies the JWT, checks `policy.yaml`, writes an audit row, then forwards.
2. **Policy engine**: role-based, **default deny** (unknown resource or role = 403).
3. **Connector** runs next to the private app and opens an **outbound** WebSocket to the gateway. The gateway never needs the app's address, and the app needs no inbound port.
4. **Audit log**: every allow and deny (user, role, resource, decision, reason) in SQLite.
5. **Fail closed**: connector offline -> `502`, request timeout -> `504`.

## Run it

```powershell
pip install fastapi uvicorn httpx pyjwt pyyaml websockets
uvicorn app.main:app --port 9000            # terminal 1: private app
uvicorn gateway.main:app --port 8000        # terminal 2: gateway
python connector\main.py                    # terminal 3: connector
$hr = python make_token.py priyam hr
curl.exe -i -H "Authorization: Bearer $hr" http://127.0.0.1:8000/hr-portal/salaries
```

| Request | Result |
|---|---|
| `hr` role token | 200 + data |
| `dev` role token | 403 (default deny) |
| no token | 401 |
| connector stopped | 502 (fail closed) |

## Design decisions

- **Outbound-only connector instead of a VPN or open inbound port:** the private app exposes nothing to the network; the connector initiates the connection.
- **Default deny:** access exists only if a rule explicitly allows it.
- **Per-request policy check:** costs some latency, but revocation and policy changes apply immediately instead of at session start.
- **Fail closed:** when the tunnel is down, requests stop instead of falling back to a direct path.
- **Audit denies too:** failed attempts are the useful signal for detecting abuse.

## Threat model

Protects against: unauthenticated access, access by a role without a rule, forged or expired tokens, an unauthorized connector (shared secret, constant-time compare), and silent fallback when the tunnel is down.

Does **not** protect against: a stolen but still valid token, a leaked connector secret, traffic sniffing (no TLS yet), denial of service (no rate limiting), or a compromised gateway host.

## Benchmarks (single laptop, k6, 20 VUs, 20 s)

| Setup | req/s | median | p95 |
|---|---|---|---|
| App directly (baseline) | X | X ms | X ms |
| Gateway, direct upstream | Y | Y ms | Y ms |
| Gateway + connector tunnel | Z | Z ms | Z ms |

Everything (k6, gateway, connector, app) shares one machine, so numbers are for **relative comparison**, not absolute capacity. Each request also does a synchronous SQLite commit, which is the main bottleneck.

## Limitations and future work

Hardcoded dev secrets, HS256 (symmetric), HTTP not HTTPS, no token revocation, no rate limiting, role-only policy (no device posture or location), query string not forwarded in direct mode, and the tunnel is simulated on one machine (not network-isolated). Next: TLS, RS256 with a login service, rate limiting, Docker private network, async audit writes.
