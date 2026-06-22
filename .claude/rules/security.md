# Rule: Security

Source: `Keel-MVP-Timeline-backend` (Authentication, API keys, Hardening), v3 §6, §13.3–§13.4. Org policy: no secrets in code/logs, least privilege, secure defaults.

## Crypto lives in one place

All cryptographic operations are in `app/core/security.py` **only**: bcrypt hash/verify (cost 12), JWT create/decode, API-key generate/hash/verify. No router or service performs crypto inline.

## Tokens

- Access JWT: 15-min expiry, returned in the response **body**. Claims: `sub` (user_id), `workspace_id`, `role`, `exp`, `iat`, `jti`.
- Refresh token: 30-day expiry, stored server-side + set as an **HttpOnly, Secure, SameSite=Lax cookie**. `POST /api/auth/refresh` rotates it. Never readable by JS; never logged.
- Login lockout: 10 fails / 15 min per email → 15-min lockout (`users.failed_login_count` + `lockout_until`).

## API keys

- Generated as `keel_sk_<random>`; only the **hash** + a short `key_prefix` persist. The secret is returned **once** at creation, never again.
- Scope `read_only` (retrieval) or `read_write` (retrieval + ingestion). Enforce scope on every dual-auth endpoint.
- Rate limit 100/min/key (sliding window, Redis) → `429` + `Retry-After`.

## Secrets & config

- All secrets are `SecretStr` in `config.py`, read from env. Never hardcode keys, hosts, or credentials. Never commit `.env`.
- Connector refresh tokens are encrypted at rest (`connector_credentials.encrypted_refresh_token`) and never logged.

## Logging & transport

- structlog only; never log passwords, tokens, API-key secrets, refresh cookies, or PII.
- CORS: explicit origin whitelist from `CORS_ALLOW_ORIGINS` (no `*`), `allow_credentials=True`.
- Every error response is the envelope `{error_code, message, request_id}` — never leak stack traces or internal messages to clients.
