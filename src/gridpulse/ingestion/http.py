import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (
        429,
        500,
        502,
        503,
        504,
    )


@retry(
    retry=retry_if_exception(_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    reraise=True,
)
def get_json(client: httpx.Client, url: str, params: dict | None = None):
    resp = client.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
