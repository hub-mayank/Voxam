"""Streaming a model-phrased reply: the provider adapters (HTTP faked), the retry rules, and the hooks down to the interviewer."""
import json

import httpx
import pytest

from app.llm.base import Reply
from app.llm.errors import ProviderError
from app.llm.graceful import GracefulLLM
from app.llm.mock import MockLLM
from app.llm.ollama import OllamaLLM
from app.llm.openai_compat import OpenAICompatLLM
from app.llm.resilient import ResilientLLM


class FakeStream:
    """Stands in for httpx.stream(...): a context manager over a list of lines."""
    def __init__(self, lines, status=200):
        self.lines, self.status_code = lines, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        yield from self.lines

    def read(self):
        return b""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"), response=httpx.Response(self.status_code))


def test_ollama_stream_delivers_pieces_and_the_final_usage(monkeypatch):
    lines = [json.dumps({"message": {"content": "Good. "}, "done": False}), json.dumps({"message": {"content": "Why?"}, "done": False}), "",
             json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 12, "eval_count": 5})]
    monkeypatch.setattr("app.llm.ollama.httpx.stream", lambda *a, **k: FakeStream(lines))
    got = []
    reply = OllamaLLM(model="m").generate_stream("s", "u", 50, got.append)
    assert got == ["Good. ", "Why?"] and reply == Reply("Good. Why?", 12, 5)


def test_openai_stream_reads_sse_chunks_and_books_the_providers_usage(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("LLM_DAILY_CALL_CAP", "1000")
    chunk = lambda **kw: "data: " + json.dumps(kw)  # noqa: E731
    lines = [chunk(choices=[{"delta": {"role": "assistant"}}]), chunk(choices=[{"delta": {"content": "Good. "}}]),
             chunk(choices=[{"delta": {"content": "Next?"}}]), chunk(choices=[], usage={"prompt_tokens": 200, "completion_tokens": 30}), "data: [DONE]"]
    seen = {}

    def fake_stream(method, url, **kw):
        seen["body"], seen["url"] = kw["json"], url
        return FakeStream(lines)
    monkeypatch.setattr("app.llm.openai_compat.httpx.stream", fake_stream)
    got = []
    llm = OpenAICompatLLM("groq", model="openai/gpt-oss-20b")
    reply = llm.generate_stream("s", "u", 50, got.append)
    assert got == ["Good. ", "Next?"] and reply.text == "Good. Next?" and (reply.tokens_in, reply.tokens_out) == (200, 30)
    assert seen["body"]["stream"] is True and seen["url"].endswith("/chat/completions")
    from app.llm.budget import token_usage
    assert token_usage()["groq|openai/gpt-oss-20b"]["tpd"] == 230, "the reservation was replaced by the real usage"


class Streams:
    provider, model, mode, name = "p", "m", "live", "p:m"

    def __init__(self, pieces=None, fail_after=None, fail_before=False):
        self.pieces, self.fail_after, self.fail_before, self.calls = pieces or ["Good. ", "Why?"], fail_after, fail_before, 0

    def generate(self, system, user, max_tokens, json_mode):
        self.calls += 1
        return Reply("".join(self.pieces))

    def generate_stream(self, system, user, max_tokens, on_delta):
        self.calls += 1
        if self.fail_before:
            raise ProviderError("down before the first piece", status="unavailable", retryable=True)
        for i, piece in enumerate(self.pieces):
            if self.fail_after is not None and i == self.fail_after:
                raise ProviderError("died midway", status="unavailable", retryable=True)
            on_delta(piece)
        return Reply("".join(self.pieces))


def test_resilient_streams_through_the_first_provider_that_can():
    llm = ResilientLLM([Streams()], retries=0)
    got = []
    assert llm.complete_text("s", "u", 50, "phrase", on_delta=got.append) == "Good. Why?"
    assert got == ["Good. ", "Why?"]


def test_a_provider_that_cannot_stream_delivers_the_whole_text_once():
    class Plain:
        provider, model, mode, name = "p", "m", "live", "p:m"

        def generate(self, system, user, max_tokens, json_mode):
            return Reply("Good. Why?")
    got = []
    assert ResilientLLM([Plain()], retries=0).complete_text("s", "u", 50, "phrase", on_delta=got.append) == "Good. Why?"
    assert got == ["Good. Why?"]


def test_failure_before_the_first_piece_falls_back_but_failure_after_it_is_raised():
    bad, good = Streams(fail_before=True), Streams(["Okay."])
    got = []
    assert ResilientLLM([bad, good], retries=0, sleep=lambda s: None).complete_text("s", "u", 50, "phrase", on_delta=got.append) == "Okay."
    assert got == ["Okay."]
    midway = Streams(fail_after=1)
    got = []
    with pytest.raises(ProviderError):
        ResilientLLM([midway, Streams(["Other."])], retries=2, sleep=lambda s: None).complete_text("s", "u", 50, "phrase", on_delta=got.append)
    assert got == ["Good. "] and midway.calls == 1, "no retry and no fallback once part of the reply was delivered"


def test_graceful_hands_a_canned_line_after_a_stream_that_died():
    llm = GracefulLLM(ResilientLLM([Streams(fail_after=1)], retries=0))
    got = []
    out = llm.complete_text("s", "ACTION: deeper\nQUESTION: q", 50, "phrase", on_delta=got.append)
    assert got == ["Good. "] and out != "Good. Why?" and "trade-offs" in out and llm.errors


def test_the_mock_delivers_its_line_through_on_delta_too():
    got = []
    text = MockLLM().complete_text("s", "ACTION: nudge", on_delta=got.append)
    assert got == [text] and MockLLM().complete_text("s", "ACTION: nudge") == text
