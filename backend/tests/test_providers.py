"""Contract tests: every provider behaves the same through generate(). HTTP is faked, so these prove
our mapping and plumbing, not that the real APIs still answer in this shape (live/real-server tests do that)."""
import json
import httpx
import pytest
from app.llm.base import Reply
from app.llm.errors import ProviderError
from app.llm.factory import make_llm
from app.llm.fake import FakeProvider
from app.llm.gemini import GeminiLLM
from app.llm.ollama import OllamaLLM
from app.llm.openai_compat import OpenAICompatLLM

REQ = httpx.Request("POST", "https://example.test")


def gemini_body(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5, "thoughtsTokenCount": 7}}


def ollama_body(text):
    return {"message": {"role": "assistant", "content": text}, "prompt_eval_count": 11, "eval_count": 5}


def openai_body(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5}}


def http_reply(behaviour, body):
    if behaviour == "timeout":
        raise httpx.ReadTimeout("slow")
    if behaviour == "connect":
        raise httpx.ConnectError("refused")
    if behaviour == "empty":
        if body in (ollama_body, openai_body):
            return httpx.Response(200, json=body(""), request=REQ)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}, request=REQ)
    if behaviour == "ok":
        return httpx.Response(200, json=body("OK"), request=REQ)
    return httpx.Response(int(behaviour), text="boom", request=REQ)


def make_gemini(monkeypatch, behaviour):
    monkeypatch.setattr("app.llm.gemini.httpx.post", lambda *a, **k: http_reply(behaviour, gemini_body))
    return GeminiLLM(model="m", api_key="k")


def make_ollama(monkeypatch, behaviour):
    monkeypatch.setattr("app.llm.ollama.httpx.post", lambda *a, **k: http_reply(behaviour, ollama_body))
    return OllamaLLM(model="m")


def make_openai(monkeypatch, behaviour):
    monkeypatch.setattr("app.llm.openai_compat.httpx.post", lambda *a, **k: http_reply(behaviour, openai_body))
    return OpenAICompatLLM("groq", model="m", api_key="k")


def make_fake(monkeypatch, behaviour):
    step = behaviour if behaviour in ("ok", "timeout") else int(behaviour) if behaviour.isdigit() else "ok"
    return FakeProvider([step], text="OK")


makers = [make_gemini, make_ollama, make_openai, make_fake]
ids = ["gemini", "ollama", "openai-compat", "fake"]


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


@pytest.mark.parametrize("maker", [make_gemini, make_ollama, make_openai], ids=["gemini", "ollama", "openai-compat"])
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


# ---------- the OpenAI-compatible adapter (Groq, Cerebras, OpenRouter, Azure Foundry style) ----------

def capture(monkeypatch):
    seen = {}

    def post(url, json=None, headers=None, params=None, timeout=None):
        seen.update(url=url, body=json, headers=headers, params=params)
        return httpx.Response(200, json=openai_body("OK"), request=REQ)

    monkeypatch.setattr("app.llm.openai_compat.httpx.post", post)
    return seen


def test_openai_request_shape_bearer(monkeypatch):
    seen = capture(monkeypatch)
    p = OpenAICompatLLM("groq", model="openai/gpt-oss-20b", api_key="sekret")
    p.generate("sys", "usr", 40, True)
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"] == {"Authorization": "Bearer sekret"} and seen["params"] is None
    b = seen["body"]
    assert b["model"] == "openai/gpt-oss-20b" and b["temperature"] == 0 and b["max_tokens"] == 40 + 1000, "reasoning headroom"
    assert b["response_format"] == {"type": "json_object"}
    assert b["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    p.generate("sys", "usr", 40, False)
    assert "response_format" not in seen["body"], "plain text asks for no JSON mode"


def test_openai_azure_style_api_key_header_and_query(monkeypatch):
    seen = capture(monkeypatch)
    env = {"AZFOUNDRY_BASE_URL": "https://res.services.ai.azure.com/models/", "AZFOUNDRY_API_KEY": "k2", "AZFOUNDRY_AUTH": "api-key",
           "AZFOUNDRY_QUERY": "api-version=2024-05-01-preview&x=1", "AZFOUNDRY_MODEL": "Phi-4"}
    p = OpenAICompatLLM("azfoundry", environ=env)
    p.generate("s", "u", 10, False)
    assert seen["url"] == "https://res.services.ai.azure.com/models/chat/completions"
    assert seen["headers"] == {"api-key": "k2"} and seen["params"] == {"api-version": "2024-05-01-preview", "x": "1"}
    assert p.name == "azfoundry:Phi-4"


def test_openai_env_options(monkeypatch):
    seen = capture(monkeypatch)
    env = {"GROQ_API_KEY": "k", "GROQ_TOKEN_HEADROOM": "0", "GROQ_JSON_MODE": "0", "GROQ_REASONING_EFFORT": "low",
           "GROQ_MAX_TOKENS_FIELD": "max_completion_tokens"}
    OpenAICompatLLM("groq", model="m", environ=env).generate("s", "u", 25, True)
    b = seen["body"]
    assert b["max_completion_tokens"] == 25 and "max_tokens" not in b and "response_format" not in b and b["reasoning_effort"] == "low"


def test_openai_needs_a_model_key_and_endpoint():
    with pytest.raises(RuntimeError, match="model"):
        OpenAICompatLLM("groq", environ={"GROQ_API_KEY": "k"})
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        OpenAICompatLLM("groq", model="m", environ={})
    with pytest.raises(RuntimeError, match="NOWHERE_BASE_URL"):
        OpenAICompatLLM("nowhere", model="m", environ={"NOWHERE_API_KEY": "k"})
    with pytest.raises(RuntimeError, match="bearer or api-key"):
        OpenAICompatLLM("groq", model="m", environ={"GROQ_API_KEY": "k", "GROQ_AUTH": "basic"})


def test_openai_reads_token_usage_content_parts_and_retry_after(monkeypatch):
    r = make_openai(monkeypatch, "ok").generate("s", "u", 5, False)
    assert (r.tokens_in, r.tokens_out) == (11, 5)
    parts = {"choices": [{"message": {"content": [{"type": "text", "text": "A"}, {"type": "text", "text": "B"}]}}]}
    monkeypatch.setattr("app.llm.openai_compat.httpx.post", lambda *a, **k: httpx.Response(200, json=parts, request=REQ))
    assert OpenAICompatLLM("groq", model="m", api_key="k").generate("s", "u", 5, False).text == "AB"
    monkeypatch.setattr("app.llm.openai_compat.httpx.post", lambda *a, **k: httpx.Response(429, headers={"Retry-After": "3"}, request=REQ))
    with pytest.raises(ProviderError) as e:
        OpenAICompatLLM("groq", model="m", api_key="k").generate("s", "u", 5, False)
    assert e.value.retry_after == 3.0 and e.value.status == "rate_limited"
    monkeypatch.setattr("app.llm.openai_compat.httpx.post", lambda *a, **k: httpx.Response(200, json={"error": {"message": "x"}}, request=REQ))
    with pytest.raises(ProviderError, match="no choices"):
        OpenAICompatLLM("groq", model="m", api_key="k").generate("s", "u", 5, False)


def test_openai_attempts_are_counted_per_provider_and_model(monkeypatch):
    from app.llm.budget import usage
    make_openai(monkeypatch, "ok").generate("s", "u", 5, False)
    with pytest.raises(ProviderError):
        make_openai(monkeypatch, "503").generate("s", "u", 5, False)  # a failed attempt is still a call
    assert usage() == {"groq|m": 2}


def test_fallback_chain_spec_with_provider_and_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    llm = make_llm("groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash-lite,ollama:llama3.2:3b")
    assert [p.name for p in llm.providers] == ["groq:openai/gpt-oss-20b", "gemini:gemini-3.5-flash-lite", "ollama:llama3.2:3b"]
    monkeypatch.setenv("GROQ_MODEL", "from-env")
    assert make_llm("groq").providers[0].model == "from-env", "no model in the spec: the provider's own env var"
    assert make_llm("groq", model="override").providers[0].model == "override", "an explicit model wins"
    monkeypatch.setenv("CEREBRAS_API_KEY", "c")
    assert make_llm("cerebras:llama3.1-8b").providers[0].base_url == "https://api.cerebras.ai/v1"
    monkeypatch.setenv("MYHOST_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("MYHOST_API_KEY", "x")
    assert make_llm("myhost:some-model").providers[0].base_url == "http://localhost:8000/v1"
    with pytest.raises(SystemExit, match="BASE_URL"):
        make_llm("unheardof:model")


def test_is_provider_name_tells_a_provider_prefix_from_a_model_with_a_colon():
    from app.llm.factory import is_provider_name, split_spec
    assert is_provider_name("groq") and is_provider_name("gemini") and is_provider_name("ollama") and is_provider_name("mock")
    assert not is_provider_name("llama3.2") and not is_provider_name("gemini-3.5-flash")
    assert split_spec("ollama:llama3.2:3b") == ("ollama", "llama3.2:3b") and split_spec("gemini") == ("gemini", None)
