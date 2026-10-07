import os
from dataclasses import dataclass


def parse_faculty_tokens(raw: str) -> dict:
    """FACULTY_TOKENS="name:token,name2:token2" -> {token: name}. The name is the reviewer identity."""
    tokens = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, token = item.partition(":")
        name, token = name.strip(), token.strip()
        if not sep or not name or not token:
            raise ValueError("FACULTY_TOKENS entries must look like name:token")
        if token.startswith("st_"):
            raise ValueError("faculty tokens must not start with st_ (reserved for student session tokens)")
        if token in tokens:
            raise ValueError("FACULTY_TOKENS has a duplicate token")
        tokens[token] = name
    return tokens


def _flag(value, default):
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


@dataclass(frozen=True)
class Settings:
    faculty_tokens: dict
    require_access_code: bool = True
    cors_origins: tuple = ()

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(parse_faculty_tokens(env.get("FACULTY_TOKENS", "")),
                   _flag(env.get("REQUIRE_ACCESS_CODE"), True), origins)
