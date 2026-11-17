"""The only way the engine may call a model endpoint.

Policy: no receipt, ID photo, face or claim detail goes to an outside AI service. Models run on
servers we or the customer control. In production (anything that is not dev or test) a model URL
must be a private host or one named in `POPS_AI_ALLOWED_HOSTS`; any other call is refused before a
byte is sent. Callers treat a refusal like any failed model call, so the case falls to a person.

Face matching and liveness never use this module: they run locally (`app/kyc/cv`).
"""

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, get_settings

_PRIVATE_NAMES = ("localhost", "127.0.0.1", "::1", "ollama")
_PRIVATE_NET = re.compile(r"^(10|192\.168|172\.(1[6-9]|2\d|3[01]))\.")


class AiBlocked(httpx.HTTPError):
    """A model URL is outside the allowed hosts. Subclasses HTTPError so every reader's
    existing 'model call failed' handling (fail closed to a person) already covers it."""


def is_private_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return (
        host in _PRIVATE_NAMES
        or host.endswith(".local")
        or host.endswith(".internal")
        or _PRIVATE_NET.match(host) is not None
    )


def host_allowed(url: str, allowed_hosts: list[str]) -> bool:
    """Private hosts always; otherwise the host must equal an allowed name or sit under it."""
    if is_private_host(url):
        return True
    host = (urlparse(url).hostname or "").lower()
    return any(host == a.lower() or host.endswith("." + a.lower()) for a in allowed_hosts)


def check(url: str, settings: Settings | None = None, *, enforce: bool | None = None) -> None:
    """Raise AiBlocked when `url` may not be called. Dev and test are not enforced."""
    s = settings or get_settings()
    on = (not s.is_dev) if enforce is None else enforce
    if on and not host_allowed(url, s.ai_allowed_hosts):
        host = urlparse(url).hostname or url
        raise AiBlocked(f"model endpoint {host} is outside POPS_AI_ALLOWED_HOSTS")


def post(url: str, **kwargs: Any) -> httpx.Response:
    """httpx.post to a model endpoint, after the allow-list check."""
    check(url)
    return httpx.post(url, **kwargs)


def endpoints(s: Settings | None = None) -> list[dict[str, Any]]:
    """Every model endpoint the engine is configured to use, for the admin status screen."""
    s = s or get_settings()
    url = s.ollama_url
    return [
        {
            "use": "receipt and ID reading, shadow proposals, AI temporary approval",
            "url": url,
            "model": s.ollama_model,
            "active": s.vlm_backend == "ollama",
            "external": not is_private_host(url),
            "allowed": host_allowed(url, s.ai_allowed_hosts),
            "api_key_set": bool(s.ollama_api_key),
        }
    ]
