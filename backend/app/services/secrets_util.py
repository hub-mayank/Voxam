"""Access codes, session tokens and signed audio URLs. Secrets come from settings (env), never from the database."""
import hashlib
import hmac
import re
import secrets

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I, L, O, 0 or 1: easy to read out loud


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def hash_code(pepper: str, viva_id: str, student_id: str, code: str) -> str:
    """HMAC-SHA256 keyed with the server secret and bound to the (viva, student), so a leaked table cannot be
    brute-forced offline without the pepper and a hash cannot be moved to another student."""
    message = "\0".join((viva_id, student_id, normalize_code(code))).encode()
    return hmac.new(pepper.encode(), message, hashlib.sha256).hexdigest()


def code_matches(pepper: str, viva_id: str, student_id: str, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_code(pepper, viva_id, student_id, code), stored_hash)


def new_session_token() -> str:
    return "st_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()  # tokens are 256-bit random: a plain hash is enough


def sign_audio(secret: str, session_id, exp: int) -> str:
    return hmac.new(secret.encode(), f"audio:{session_id}:{exp}".encode(), hashlib.sha256).hexdigest()


def audio_signature_ok(secret: str, session_id, exp: int, sig: str, now_ts: float) -> bool:
    return exp > now_ts and hmac.compare_digest(sign_audio(secret, session_id, exp), sig or "")
