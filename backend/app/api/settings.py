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
    contract_stub: bool = False       # CONTRACT_STUB=1: every route returns its example (Friend A's mock backend)
    access_code_pepper: str = ""      # ACCESS_CODE_PEPPER: server-side secret for HMAC-hashing access codes
    audio_signing_secret: str = ""    # AUDIO_SIGNING_SECRET: signs the expiring audio URLs
    database_url: str = ""            # DATABASE_URL; empty means the default local SQLite file
    llm_chain: str = ""               # LLM_CHAIN for the live interviewer; empty means mock
    code_delay_cap_seconds: int = 60  # CODE_DELAY_CAP_SECONDS: after n wrong codes the next try waits min(cap, 2^(n-1)) s
    ip_failures_per_minute: int = 30  # IP_FAILURES_PER_MINUTE: wrong codes one client IP may send per minute (all students)
    trust_forwarded_for: bool = False  # TRUST_FORWARDED_FOR=1 behind a reverse proxy: use the first X-Forwarded-For address
    answer_lease_seconds: int = 60    # ANSWER_LEASE_SECONDS: longest one answer may be processed before another worker takes over

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            parse_faculty_tokens(env.get("FACULTY_TOKENS", "")),
            _flag(env.get("REQUIRE_ACCESS_CODE"), True), origins,
            contract_stub=_flag(env.get("CONTRACT_STUB"), False),
            access_code_pepper=env.get("ACCESS_CODE_PEPPER", ""),
            audio_signing_secret=env.get("AUDIO_SIGNING_SECRET", ""),
            database_url=env.get("DATABASE_URL", ""),
            llm_chain=env.get("LLM_CHAIN", ""),
            code_delay_cap_seconds=int(env.get("CODE_DELAY_CAP_SECONDS", 60)),
            ip_failures_per_minute=int(env.get("IP_FAILURES_PER_MINUTE", 30)),
            trust_forwarded_for=_flag(env.get("TRUST_FORWARDED_FOR"), False),
            answer_lease_seconds=int(env.get("ANSWER_LEASE_SECONDS", 60)))

    def check(self):
        """Real mode refuses to start without its secrets. Stub mode needs none."""
        if self.contract_stub:
            return
        if len(self.audio_signing_secret) < 16:
            raise ValueError("AUDIO_SIGNING_SECRET (at least 16 characters) is required unless CONTRACT_STUB=1")
        if self.require_access_code and len(self.access_code_pepper) < 16:
            raise ValueError("ACCESS_CODE_PEPPER (at least 16 characters) is required unless REQUIRE_ACCESS_CODE=false or CONTRACT_STUB=1")
