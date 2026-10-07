import httpx


class ProviderError(RuntimeError):
    """status: rate_limited | unavailable | timeout | error (same words as telemetry)."""

    def __init__(self, message: str, status: str = "error", retryable: bool = False,
                 status_code: int | None = None, retry_after: float | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = retry_after
        self.body = body


class AllProvidersFailed(ProviderError):
    pass


def from_status(code: int, retry_after: float | None = None, body: str = "") -> ProviderError:
    if code == 429:
        status, retryable = "rate_limited", True
    elif code == 408:
        status, retryable = "timeout", True
    elif code >= 500:
        status, retryable = "unavailable", True
    else:
        status, retryable = "error", False
    return ProviderError(f"HTTP {code}", status, retryable, code, retry_after, body[:500])


def from_httpx(exc: httpx.HTTPError) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        header = exc.response.headers.get("retry-after", "")
        try:
            retry_after = float(header)
        except ValueError:
            retry_after = None
        return from_status(exc.response.status_code, retry_after, exc.response.text)
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError("timed out", "timeout", True)
    if isinstance(exc, httpx.TransportError):
        return ProviderError(f"connection failed: {type(exc).__name__}", "unavailable", True)
    return ProviderError(f"http error: {type(exc).__name__}")
