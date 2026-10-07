"""Contract-phase helpers: every stub route answers with its schema's example and `X-Contract-Stub: 1`."""
import io
import wave

from fastapi import Request, Response

from .errors import ERROR_EXAMPLES, ApiError, ErrorCode

STUB_HEADER = "X-Contract-Stub"


def stub_marker(request: Request, response: Response):
    """Router dependency for stub routes. Remove it from a router when its real handlers land.
    Send `X-Mock-Error: <code>` to make any stub route fail with that error code and its example details."""
    if not request.app.state.settings.contract_stub:
        return
    wanted = request.headers.get("x-mock-error")
    if wanted:
        try:
            code = ErrorCode(wanted)
        except ValueError:
            raise ApiError(ErrorCode.validation_error, f"unknown X-Mock-Error {wanted!r}",
                           {"allowed": [c.value for c in ErrorCode]})
        raise ApiError(code, details=ERROR_EXAMPLES[code][1])
    response.headers[STUB_HEADER] = "1"


def silent_wav(seconds=1, rate=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


def byte_range(header, size):
    """Parse a single `bytes=start-end` Range header -> (start, end) inclusive, or None for no header."""
    if not header:
        return None
    try:
        unit, _, spec = header.partition("=")
        first, _, last = spec.strip().partition("-")
        if unit.strip() != "bytes" or "," in spec:
            raise ValueError
        if first == "":  # suffix: last N bytes
            start, end = max(size - int(last), 0), size - 1
        else:
            start, end = int(first), (int(last) if last else size - 1)
    except ValueError:
        raise ApiError(ErrorCode.range_not_satisfiable, "Unsupported Range header.", {"size_bytes": size})
    end = min(end, size - 1)
    if start > end or start >= size:
        raise ApiError(ErrorCode.range_not_satisfiable, details={"size_bytes": size})
    return start, end
