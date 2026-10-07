"""Contract tests: every provider behaves the same through generate(). HTTP is faked, so these prove
our mapping and plumbing, not that the real APIs still answer in this shape (live/real-server tests do that)."""
import json
import httpx
import pytest
from app.llm.base import Reply
from app.llm.errors import ProviderError
from app.llm.fake import FakeProvider
from app.llm.gemini import GeminiLLM
from app.llm.ollama import OllamaLLM

REQ = httpx.Request("POST", "https://example.test")


def gemini_body(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5, "thoughtsTokenCount": 7}}


def ollama_body(text):
    return {"message": {"role": "assistant", "content": text}, "prompt_eval_count": 11, "eval_count": 5}


def http_reply(behaviour, body):
    if behaviour == "timeout":
        raise httpx.ReadTimeout("slow")
    if behaviour == "connect":
        raise httpx.ConnectError("refused")
    if behaviour == "empty":
        return httpx.Response(200, json=body(""), request=REQ) if body is ollama_body else \
            httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}, request=REQ)
    if behaviour == "ok":
        return httpx.Response(200, json=body("OK"), request=REQ)
    return httpx.Response(int(behaviour), text="boom", request=REQ)


def make_gemini(monkeypatch, behaviour):
    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **k: http_reply(behaviour, gemini_body))
    return GeminiLLM(model="m", api_key="k")


def make_ollama(monkeypatch, behaviour):
    monkeypatch.setattr("app.llm.ollama.httpx.post", lambda *a, **k: http_reply(behaviour, ollama_body))
    return OllamaLLM(model="m")


def make_fake(monkeypatch, behaviour):
    step = behaviour if behaviour in ("ok", "timeout") else int(behaviour) if behaviour.isdigit() else "ok"
    return FakeProvider([step], text="OK")


makers = [make_gemini, make_ollama, make_fake]
ids = ["gemini", "ollama", "fake"]


@pytest.fixture(params=makers, ids=ids)
def make(request, monkeypatch):
    return lambda behaviour: request.param(monkeypatch, behaviour)


def test_ok_reply(make):
    p = make("ok")
    r = p.generate("sys", "user words here", 50, False)
    assert isinstance(r, Reply) and r.text == "OK"
    assert r.tokens_in is None or type(r.tokens_in) is int
    assert r.tokens_out is None or type(r.tokens_out) is int
    assert p.name == f"{p.provider}:{p.model}" and p.mode in ("live", "stub")


@pytest.mark.parametrize("behaviour,status,retryable", [
    ("429", "rate_limited", True), ("503", "unavailable", True), ("500", "unavailable", True),
    ("timeout", "timeout", True), ("404", "error", False), ("400", "error", False)])
def test_failures_are_mapped(make, behaviour, status, retryable):
    with pytest.raises(ProviderError) as e:
        make(behaviour).generate("s", "u", 50, False)
    assert (e.value.status, e.value.retryable) == (status, retryable)


@pytest.mark.parametrize("maker", [make_gemini, make_ollama], ids=["gemini", "ollama"])
def test_http_providers_map_transport_and_empty(maker, monkeypatch):
    with pytest.raises(ProviderError) as e:
        maker(monkeypatch, "connect").generate("s", "u", 50, False)
    assert (e.value.status, e.value.retryable) == ("unavailable", True)
    with pytest.raises(ProviderError) as e:
        maker(monkeypatch, "empty").generate("s", "u", 50, False)
    assert (e.value.status, e.value.retryable) == ("error", False)


def test_retry_after_header_is_read(monkeypatch):
    resp = httpx.Response(429, headers={"Retry-After": "7"}, request=REQ)
    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **k: resp)
    with pytest.raises(ProviderError) as e:
        GeminiLLM(model="m", api_key="k").generate("s", "u", 50, False)
    assert e.value.retry_after == 7.0 and e.value.status_code == 429


def test_gemini_token_usage_counts_thinking_as_output(monkeypatch):
    r = make_gemini(monkeypatch, "ok").generate("s", "u", 50, False)
    assert (r.tokens_in, r.tokens_out) == (11, 12)


def test_ollama_request_shape(monkeypatch):
    seen = {}

    def post(url, json=None, timeout=None):
        seen.update(url=url, body=json)
        return httpx.Response(200, json=ollama_body("{}"), request=REQ)

    monkeypatch.setattr("app.llm.ollama.httpx.post", post)
    OllamaLLM(model="llama3.2", host="http://h:1/").generate("sys", "usr", 40, True)
    assert seen["url"] == "http://h:1/api/chat"
    assert seen["body"]["format"] == "json" and seen["body"]["stream"] is False
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_fake_script_repeats_last_step():
    p = FakeProvider([429, "ok"])
    with pytest.raises(ProviderError):
        p.generate("s", "u", 5, False)
    assert [p.generate("s", "u", 5, False).text for _ in range(2)] == ["Okay, let's move on."] * 2
    assert json.loads(p.generate("s", "u", 5, True).text) == {"quality": "partial"}


def test_ollama_needs_model(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        OllamaLLM()


def real_ollama():
    import os
    model = os.environ.get("OLLAMA_MODEL")
    return OllamaLLM(model=model) if model else None


@pytest.mark.skipif(not (real_ollama() and real_ollama().available()),
                    reason="no Ollama server with OLLAMA_MODEL pulled")
def test_real_ollama_contract():
    p = real_ollama()
    r = p.generate("Reply with one word.", "Say hello.", 20, False)
    assert r.text.strip()
    data = json.loads(p.generate("Reply with JSON like {\"ok\": true}.", "go", 40, True).text)
    assert isinstance(data, dict)
