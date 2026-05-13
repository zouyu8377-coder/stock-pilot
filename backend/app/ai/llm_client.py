import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import APITimeoutError, OpenAI


def _load_env():
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)


_load_env()

BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_CONNECT_TIMEOUT_SECONDS = float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "10"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "0"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1800"))
LLM_STREAM = os.getenv("LLM_STREAM", "true").lower() in {"1", "true", "yes", "on"}
LLM_USE_JSON_MODE = os.getenv("LLM_USE_JSON_MODE", "false").lower() in {"1", "true", "yes", "on"}
DEFAULT_THINKING_TYPE = "disabled" if (MODEL_NAME or "").startswith("kimi-k2.") else ""
LLM_THINKING_TYPE = os.getenv("LLM_THINKING_TYPE", DEFAULT_THINKING_TYPE).strip().lower()
DEFAULT_TEMPERATURE = "0.6" if LLM_THINKING_TYPE == "disabled" and (MODEL_NAME or "").startswith("kimi-k2.") else "0.1"
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", DEFAULT_TEMPERATURE))

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=httpx.Timeout(
        timeout=LLM_TIMEOUT_SECONDS,
        connect=LLM_CONNECT_TIMEOUT_SECONDS,
    ),
    max_retries=LLM_MAX_RETRIES,
)


def _build_payload(prompt: str, use_json_mode: bool) -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "你是一位专业A股交易员。只输出JSON，不要输出markdown，不要输出解释文字。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if use_json_mode:
        payload["response_format"] = {"type": "json_object"}
    if LLM_THINKING_TYPE in {"enabled", "disabled"}:
        payload["extra_body"] = {"thinking": {"type": LLM_THINKING_TYPE}}
    return payload


def _request_completion(prompt: str, use_json_mode: bool) -> str:
    payload = _build_payload(prompt, use_json_mode)

    if not LLM_STREAM:
        response = client.chat.completions.create(**payload)
        return response.choices[0].message.content or ""

    stream = client.chat.completions.create(**payload, stream=True)
    chunks: list[str] = []
    first_chunk_at: float | None = None
    started = time.perf_counter()

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if not text:
            continue
        if first_chunk_at is None:
            first_chunk_at = time.perf_counter()
            print(f"[LLM] First stream chunk in {first_chunk_at - started:.1f}s")
        chunks.append(text)

    return "".join(chunks)


def call_llm(prompt: str) -> str:
    started = time.perf_counter()
    print(
        "[LLM] Sending request: "
        f"model={MODEL_NAME}, timeout={LLM_TIMEOUT_SECONDS:.0f}s, "
        f"retries={LLM_MAX_RETRIES}, stream={LLM_STREAM}, "
        f"max_tokens={LLM_MAX_TOKENS}, thinking={LLM_THINKING_TYPE or 'default'}, "
        f"temperature={LLM_TEMPERATURE}, json_mode={LLM_USE_JSON_MODE}"
    )
    try:
        content = _request_completion(prompt, LLM_USE_JSON_MODE)
        elapsed = time.perf_counter() - started
        print(f"[LLM] Provider response received in {elapsed:.1f}s")
        return content

    except APITimeoutError as e:
        elapsed = time.perf_counter() - started
        print(f"[LLM] Provider timed out in {elapsed:.1f}s: {e}")
        raise

    except Exception as e:
        elapsed = time.perf_counter() - started
        print(f"[LLM] First attempt failed in {elapsed:.1f}s: {e}")

        if not LLM_USE_JSON_MODE:
            raise

        try:
            retry_started = time.perf_counter()
            content = _request_completion(prompt, False)
            retry_elapsed = time.perf_counter() - retry_started
            print(f"[LLM] Non-JSON-mode retry received in {retry_elapsed:.1f}s")
            return content
        except Exception as e2:
            print(f"[LLM] Second attempt also failed: {e2}")
            raise
