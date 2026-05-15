"""
ollama_client.py  — Ollama HTTP wrapper  (FIXED v1.1)

BUGS FIXED
──────────
1. Timeout too short (180 s) — bumped default to 600 s.
2. No streaming — the old client waited for the ENTIRE response before
   returning, so one slow token killed the whole request with a ReadTimeout.
   Now uses stream=True + chunked reading so the connection stays alive for
   as long as Ollama keeps writing tokens.
3. No retry logic — added up to 2 automatic retries on timeout.
4. Health check now also returns the list of local models so the frontend
   can warn the user if the selected model isn't pulled yet.
"""

import json
import logging
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ── Default timeout (seconds) ─────────────────────────────────────────────────
# llama3.2 on a mid-range laptop can take 5-8 minutes for a long resume prompt.
# Set this high; the streaming approach keeps the HTTP connection alive so the
# OS-level socket timeout (which caused the old ReadTimeout) no longer fires.
DEFAULT_TIMEOUT = 600   # 10 minutes
RETRY_COUNT     = 2     # retry up to 2 times on timeout before giving up


def _get_ollama_url() -> str:
    """Read OLLAMA_URL lazily so tests don't need a live server."""
    try:
        from config.settings import settings
        return settings.OLLAMA_URL.rstrip("/")
    except Exception:
        return "http://localhost:11434"


def _get_model() -> str:
    try:
        from config.settings import settings
        return settings.OLLAMA_MODEL
    except Exception:
        return "llama3.2"


# ─────────────────────────────────────────────────────────────────────────────
# Core generate — streaming to avoid ReadTimeout
# ─────────────────────────────────────────────────────────────────────────────

def ollama_generate(prompt: str, model: Optional[str] = None,
                    timeout: int = DEFAULT_TIMEOUT,
                    num_predict: int = 4096) -> str:
    """
    Send a prompt to Ollama and return the full generated text.

    Uses HTTP streaming so the socket stays alive while Ollama generates tokens
    — this prevents the urllib3 ReadTimeout that occurred with stream=False.
    Retries up to RETRY_COUNT times on timeout.

    Parameters
    ----------
    prompt      : the full prompt text
    model       : override the configured model name
    timeout     : seconds before giving up (per attempt)
    num_predict : max tokens to generate (use 8192 for 2-page verbose resumes)
    """
    url   = f"{_get_ollama_url()}/api/generate"
    model = model or _get_model()

    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_predict": num_predict,   # caller controls token budget
        },
    }

    last_exc = None
    for attempt in range(1, RETRY_COUNT + 2):   # 1 … RETRY_COUNT+1 attempts
        try:
            if attempt > 1:
                log.warning("Ollama retry %d/%d …", attempt, RETRY_COUNT + 1)
                time.sleep(2)

            with requests.post(url, json=payload, stream=True,
                               timeout=timeout) as resp:
                resp.raise_for_status()

                full_text = []
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("response", "")
                    full_text.append(token)
                    if chunk.get("done", False):
                        break

                return "".join(full_text)

        except requests.exceptions.Timeout as exc:
            last_exc = exc
            log.warning("Ollama timeout on attempt %d (timeout=%ds)", attempt, timeout)
        except requests.exceptions.ConnectionError as exc:
            raise TimeoutError(
                f"Cannot connect to Ollama at {_get_ollama_url()}. "
                "Make sure Ollama is running:  ollama serve"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response else "?"
            raise RuntimeError(f"Ollama HTTP {status}: {exc}") from exc

    raise TimeoutError(
        f"Ollama timed out after {timeout}s ({RETRY_COUNT + 1} attempts). "
        "Try a smaller/faster model, or increase DEFAULT_TIMEOUT in ollama_client.py.\n"
        "Quick fixes:\n"
        "  • Run:  ollama pull llama3.2:1b   (much faster 1-billion param model)\n"
        "  • Or set OLLAMA_MODEL=llama3.2:1b in your .env file"
    ) from last_exc


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

def ollama_health() -> dict:
    """
    Returns {"status": "ok"|"error", "models": [...], "message": "..."}.
    Used by /api/status and /api/ollama/test.
    """
    base = _get_ollama_url()
    try:
        # /api/tags lists all locally pulled models
        r = requests.get(f"{base}/api/tags", timeout=5)
        r.raise_for_status()
        data   = r.json()
        models = [m["name"] for m in data.get("models", [])]
        current_model = _get_model()

        if not models:
            return {
                "status":  "warning",
                "models":  [],
                "message": (
                    "Ollama is running but no models are pulled. "
                    f"Run:  ollama pull {current_model}"
                ),
            }

        if current_model not in models:
            # Accept partial matches like "llama3.2" matching "llama3.2:latest"
            matched = any(m.startswith(current_model) for m in models)
            if not matched:
                return {
                    "status":  "warning",
                    "models":  models,
                    "message": (
                        f"Model '{current_model}' is not pulled. "
                        f"Available: {', '.join(models)}. "
                        f"Run:  ollama pull {current_model}"
                    ),
                }

        return {"status": "ok", "models": models, "message": "Ollama is ready"}

    except requests.exceptions.ConnectionError:
        return {
            "status":  "error",
            "models":  [],
            "message": (
                f"Cannot reach Ollama at {base}. "
                "Start it with:  ollama serve"
            ),
        }
    except Exception as exc:
        return {"status": "error", "models": [], "message": str(exc)}