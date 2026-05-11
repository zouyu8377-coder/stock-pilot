import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


def _load_env():
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)


_load_env()

BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL")

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


def call_llm(prompt: str) -> str:
    try:
        # Try with response_format for strict JSON (火山引擎新版API支持)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "你是一位专业A股交易员。只输出JSON，不要输出markdown，不要输出解释文字。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"[LLM] First attempt failed: {e}")

        # Fallback without response_format
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业A股交易员。只输出JSON，不要输出markdown，不要输出解释文字。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
            )
            return response.choices[0].message.content

        except Exception as e2:
            print(f"[LLM] Second attempt also failed: {e2}")
            raise