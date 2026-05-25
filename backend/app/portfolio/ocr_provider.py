from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from app.core.config import settings


PORTFOLIO_VISION_EXTRACTION_PROMPT = """
你是证券持仓截图结构化提取器，不是投资顾问。

请仅根据图片中清晰可见的文字和数字，提取账户摘要与持仓行数据，返回严格 JSON。
不得推测图片中不存在的信息，不得补全不清晰数字，不得提供投资分析或买卖建议。
对于不确定字段，返回 null，并在 warnings 中说明。
股票代码与股票名称仅提取图片可见原文，后续由本地系统标准化校验。

返回结构必须等价于：
{
  "source_view": {
    "platform_guess": "同花顺或 null",
    "screenshot_displayed_time": null,
    "warnings": []
  },
  "account_summary": {
    "total_assets": null,
    "cash_available": null,
    "total_market_value": null,
    "total_unrealized_pnl": null,
    "repo_amount": null,
    "repo_available_date": null
  },
  "holdings": [
    {
      "raw_symbol": null,
      "raw_name": null,
      "quantity": null,
      "available_quantity": null,
      "avg_cost": null,
      "screenshot_price": null,
      "market_value": null,
      "unrealized_pnl": null,
      "unrealized_pnl_pct": null,
      "warnings": []
    }
  ],
  "unrecognized_text": [],
  "parse_warnings": []
}
图片未显示的字段必须返回 null。不要输出投资建议或买卖结论。
""".strip()


@dataclass
class OcrResult:
    provider_name: str
    status: str
    raw_text: str = ""
    warnings: list[str] | None = None
    structured_payload: dict[str, Any] | None = None
    error_summary: str | None = None


class PortfolioImageParserProvider(Protocol):
    provider_name: str

    def parse_image(self, image_path: Path) -> OcrResult:
        ...


class LocalOcrProvider:
    provider_name = "local_noop"

    def parse_image(self, image_path: Path) -> OcrResult:
        return self.extract_text(image_path)

    def extract_text(self, image_path: Path) -> OcrResult:
        sidecar = image_path.with_suffix(image_path.suffix + ".txt")
        if sidecar.exists():
            return OcrResult(
                provider_name="local_sidecar_text",
                status="partial",
                raw_text=sidecar.read_text(encoding="utf-8"),
                warnings=["使用本地同名文本文件作为可审计 OCR 输入。"],
            )
        return OcrResult(
            provider_name=self.provider_name,
            status="failed_manual_entry_required",
            raw_text="",
            warnings=["当前未启用云端视觉解析；已保留截图并创建可手工补录的草稿。"],
        )


LocalNoopPortfolioImageParser = LocalOcrProvider


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        parsed = json.loads(fenced.group(1))
        if isinstance(parsed, dict):
            return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("model response is not strict JSON")


def volcengine_ark_vision_status() -> dict[str, Any]:
    if not settings.VOLCENGINE_ARK_VISION_ENABLED:
        return {
            "provider": "volcengine_ark_vision",
            "status": "disabled",
            "enabled": False,
            "configured": False,
        }
    missing = [
        name
        for name, value in {
            "VOLCENGINE_ARK_VISION_BASE_URL": settings.VOLCENGINE_ARK_VISION_BASE_URL,
            "VOLCENGINE_ARK_VISION_API_KEY": settings.VOLCENGINE_ARK_VISION_API_KEY,
            "VOLCENGINE_ARK_VISION_MODEL": settings.VOLCENGINE_ARK_VISION_MODEL,
        }.items()
        if not value
    ]
    if missing:
        return {
            "provider": "volcengine_ark_vision",
            "status": "misconfigured",
            "enabled": True,
            "configured": False,
            "missing": missing,
        }
    return {
        "provider": "volcengine_ark_vision",
        "status": "configured_not_verified",
        "enabled": True,
        "configured": True,
        "model": settings.VOLCENGINE_ARK_VISION_MODEL,
        "base_url_configured": True,
        "api_key_configured": True,
        "timeout_seconds": settings.VOLCENGINE_ARK_VISION_TIMEOUT,
    }


class VolcengineArkVisionPortfolioImageParser:
    provider_name = "volcengine_ark_vision"

    def __init__(self, http_post: Any | None = None):
        self.http_post = http_post or requests.post

    def parse_image(self, image_path: Path) -> OcrResult:
        status = volcengine_ark_vision_status()
        if status["status"] != "configured_not_verified":
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                warnings=[f"云端视觉解析不可用：{status['status']}"],
                error_summary=status["status"],
            )
        try:
            image_bytes = image_path.read_bytes()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }.get(image_path.suffix.lower(), "image/png")
            data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
            url = settings.VOLCENGINE_ARK_VISION_BASE_URL.rstrip("/")
            if not url.endswith("/chat/completions"):
                url = f"{url}/chat/completions"
            payload: dict[str, Any] = {
                "model": settings.VOLCENGINE_ARK_VISION_MODEL,
                "messages": [
                    {"role": "system", "content": PORTFOLIO_VISION_EXTRACTION_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请仅提取这张持仓截图中的账户摘要和持仓行，返回严格 JSON。"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                "max_tokens": settings.VOLCENGINE_ARK_VISION_MAX_TOKENS,
                "temperature": 0,
            }
            if settings.VOLCENGINE_ARK_VISION_JSON_MODE:
                payload["response_format"] = {"type": "json_object"}
            response = self.http_post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.VOLCENGINE_ARK_VISION_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=settings.VOLCENGINE_ARK_VISION_TIMEOUT,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                body = (response.text or "")[:500]
                raise RuntimeError(f"HTTP {response.status_code}: {body}") from exc
            data = response.json()
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            parsed = _extract_json_object(str(content))
            return OcrResult(
                provider_name=self.provider_name,
                status="draft_parsed",
                raw_text="[cloud vision structured JSON omitted]",
                warnings=["云端视觉识别结果为待核对草稿，确认前不会写入正式账户快照。"],
                structured_payload=parsed,
            )
        except requests.Timeout as exc:
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                raw_text="",
                warnings=[f"云端视觉识别超时，已转为可编辑草稿。当前超时阈值为 {settings.VOLCENGINE_ARK_VISION_TIMEOUT} 秒。"],
                error_summary=f"timeout after {settings.VOLCENGINE_ARK_VISION_TIMEOUT}s",
            )
        except Exception as exc:
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                raw_text="",
                warnings=[f"云端视觉识别失败，已转为可编辑草稿：{str(exc)[:300]}"],
                error_summary=str(exc)[:300],
            )
