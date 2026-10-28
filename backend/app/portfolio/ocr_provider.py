from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

import requests
from PIL import Image

from app.core.config import settings


PORTFOLIO_VISION_EXTRACTION_PROMPT = """
你是证券持仓截图结构化提取器，不是投资顾问。

任务：仅提取图片中清晰可见的账户摘要和全部持仓行。
规则：
1. 只输出一个 JSON 对象；禁止 Markdown、代码围栏、解释和思考过程。
2. 不得推测、补全或给出投资建议；图片未显示或不确定的字段必须为 null。
3. 成本/现价通常在同一列上下排列，必须按表头顺序读取。
4. 异常负成本、负盈亏或异常百分比必须保留图片原值，不得修正。
5. 股票代码不可见时 raw_symbol=null，不得用名称代替代码。
6. warnings 每行最多 2 条，parse_warnings 最多 4 条，每条不超过 40 个汉字。
7. 禁止增加下列结构之外的字段，数值不得带逗号、货币符号或百分号。

输出结构：
{
  "source_view": {
    "platform_guess": null,
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
""".strip()
PORTFOLIO_VISION_COMPACT_PROMPT = """
你是证券持仓截图结构化提取器，不是投资顾问。

任务：仅提取图片中清晰可见的账户摘要和持仓行。必须只输出紧凑 JSON，不得输出解释、思考过程、Markdown 或代码围栏。

规则：
1. 不得推测；看不清、未显示或无法确认的值必须是 null。
2. 股票代码不可见时填 null，不得用名称编造代码。
3. 成本/现价按图片表头顺序读取；负成本、负盈亏按图片原值保留。
4. 数字不得带逗号、货币符号、百分号或单位。
5. 只允许输出 v、a、h、w 四个键；w 最多 3 条极短警告。不要逐行解释。

输出结构：
{"v":3,"a":[总资产,可用现金,总市值,总盈亏,逆回购金额,逆回购到期日],"h":[[名称,代码,持仓数量,可用数量,成本,现价,市值,浮盈亏,浮盈亏百分比]],"w":[]}
""".strip()

PORTFOLIO_VISION_PROMPT_VERSION = "portfolio_vision.minimax.v3.compact"
PORTFOLIO_VISION_SEGMENT_PROMPT_VERSION = "portfolio_vision.minimax.v3.segment"
TRADE_VISION_PROMPT_VERSION = "trade_vision.minimax.v1"
TRADE_VISION_EXTRACTION_PROMPT = """
你是证券成交截图结构化提取器，不是投资顾问。

任务：仅提取图片中清晰可见的全部成交记录。
规则：
1. 只输出一个 JSON 对象；禁止 Markdown、代码围栏、解释和思考过程。
2. 不得推测代码、成交日期或其他未显示信息；未显示字段必须为 null。
3. 买入标准化为 buy，卖出标准化为 sell。
4. 必须分别提取成交均价、成交量和成交额，不得使用行情现价替代。
5. 数值不得带逗号、货币符号或单位；异常值按图片原文保留。
6. warnings 每行最多 2 条，parse_warnings 最多 4 条，每条不超过 40 个汉字。
7. 禁止增加下列结构之外的字段。

输出结构：
{
  "source_view": {
    "platform_guess": null,
    "screenshot_displayed_time": null,
    "warnings": []
  },
  "transactions": [
    {
      "raw_symbol": null,
      "raw_name": null,
      "side": null,
      "average_price": null,
      "quantity": null,
      "amount": null,
      "occurred_at": null,
      "warnings": []
    }
  ],
  "parse_warnings": []
}
""".strip()
MAX_HOLDING_ROWS = 80
MAX_WARNING_ITEMS = 4
MAX_WARNING_LENGTH = 80
VISION_SEGMENT_HEIGHT = 1200
VISION_SEGMENT_OVERLAP = 200


class VisionOutputLengthError(ValueError):
    def __init__(self, usage: dict[str, int], finish_reason: str | None):
        super().__init__("模型输出达到 token 上限，已拒绝不完整 JSON")
        self.usage = usage
        self.finish_reason = finish_reason


class VisionStructuredOutputError(ValueError):
    def __init__(self, message: str, usage: dict[str, int], finish_reason: str | None):
        super().__init__(message)
        self.usage = usage
        self.finish_reason = finish_reason


@dataclass
class OcrResult:
    provider_name: str
    status: str
    raw_text: str = ""
    warnings: list[str] | None = None
    structured_payload: dict[str, Any] | None = None
    error_summary: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


class PortfolioImageParserProvider(Protocol):
    provider_name: str

    def parse_image(self, image_path: Path, screenshot_kind: str = "current_holdings") -> OcrResult:
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


def _warnings(value: Any, limit: int = MAX_WARNING_ITEMS) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()[:MAX_WARNING_LENGTH]
        for item in value[:limit]
        if str(item).strip()
    ]


def _normalize_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "h" in payload:
        return _normalize_compact_holding_payload(payload)
    source = payload.get("source_view") if isinstance(payload.get("source_view"), dict) else {}
    account = payload.get("account_summary") if isinstance(payload.get("account_summary"), dict) else {}
    account_fields = (
        "total_assets",
        "cash_available",
        "total_market_value",
        "total_unrealized_pnl",
        "repo_amount",
        "repo_available_date",
    )
    holding_fields = (
        "raw_symbol",
        "raw_name",
        "quantity",
        "available_quantity",
        "avg_cost",
        "screenshot_price",
        "market_value",
        "unrealized_pnl",
        "unrealized_pnl_pct",
    )
    holdings: list[dict[str, Any]] = []
    for item in (payload.get("holdings") or [])[:MAX_HOLDING_ROWS]:
        if not isinstance(item, dict):
            continue
        row = {key: item.get(key) for key in holding_fields}
        row["warnings"] = _warnings(item.get("warnings"), limit=2)
        holdings.append(row)
    return {
        "source_view": {
            "platform_guess": source.get("platform_guess"),
            "screenshot_displayed_time": source.get("screenshot_displayed_time"),
            "warnings": _warnings(source.get("warnings")),
        },
        "account_summary": {key: account.get(key) for key in account_fields},
        "holdings": holdings,
        "unrecognized_text": _warnings(payload.get("unrecognized_text")),
        "parse_warnings": _warnings(payload.get("parse_warnings")),
    }


def _normalize_compact_holding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    account_fields = (
        "total_assets",
        "cash_available",
        "total_market_value",
        "total_unrealized_pnl",
        "repo_amount",
        "repo_available_date",
    )
    holding_fields = (
        "raw_name",
        "raw_symbol",
        "quantity",
        "available_quantity",
        "avg_cost",
        "screenshot_price",
        "market_value",
        "unrealized_pnl",
        "unrealized_pnl_pct",
    )
    account_values = payload.get("a") if isinstance(payload.get("a"), list) else []
    account = {
        field: account_values[index] if index < len(account_values) else None
        for index, field in enumerate(account_fields)
    }
    holdings: list[dict[str, Any]] = []
    for item in (payload.get("h") or [])[:MAX_HOLDING_ROWS]:
        if isinstance(item, list):
            row = {
                field: item[index] if index < len(item) else None
                for index, field in enumerate(holding_fields)
            }
        elif isinstance(item, dict):
            row = {field: item.get(field) for field in holding_fields}
        else:
            continue
        row["warnings"] = []
        holdings.append(row)
    return {
        "source_view": {
            "platform_guess": None,
            "screenshot_displayed_time": None,
            "warnings": [],
        },
        "account_summary": account,
        "holdings": holdings,
        "unrecognized_text": [],
        "parse_warnings": _warnings(payload.get("w"), limit=3),
    }


def _normalize_trade_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source_view") if isinstance(payload.get("source_view"), dict) else {}
    transactions: list[dict[str, Any]] = []
    fields = ("raw_symbol", "raw_name", "side", "average_price", "quantity", "amount", "occurred_at")
    for item in (payload.get("transactions") or [])[:MAX_HOLDING_ROWS]:
        if not isinstance(item, dict):
            continue
        row = {key: item.get(key) for key in fields}
        row["warnings"] = _warnings(item.get("warnings"), limit=2)
        transactions.append(row)
    return {
        "source_view": {
            "platform_guess": source.get("platform_guess"),
            "screenshot_displayed_time": source.get("screenshot_displayed_time"),
            "warnings": _warnings(source.get("warnings")),
        },
        "transactions": transactions,
        "parse_warnings": _warnings(payload.get("parse_warnings")),
    }


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
        "max_output_tokens": settings.VOLCENGINE_ARK_VISION_MAX_TOKENS,
        "retry_max_output_tokens": settings.VOLCENGINE_ARK_VISION_RETRY_MAX_TOKENS,
        "segment_max_output_tokens": settings.VOLCENGINE_ARK_VISION_SEGMENT_MAX_TOKENS,
        "thinking_mode": settings.VOLCENGINE_ARK_VISION_THINKING_MODE,
        "prompt_version": PORTFOLIO_VISION_PROMPT_VERSION,
    }


class VolcengineArkVisionPortfolioImageParser:
    provider_name = "volcengine_ark_vision"

    def __init__(self, http_post: Any | None = None):
        self.http_post = http_post or requests.post

    @staticmethod
    def _mime_for_path(image_path: Path) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(image_path.suffix.lower(), "image/png")

    @staticmethod
    def _usage(data: dict[str, Any], *, attempts: int = 1) -> dict[str, int]:
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "attempts": attempts,
        }

    def _request(
        self,
        *,
        image_bytes: bytes,
        mime: str,
        prompt: str,
        user_instruction: str,
        max_tokens: int,
        trade_mode: bool,
    ) -> tuple[dict[str, Any], str | None, dict[str, int]]:
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        url = settings.VOLCENGINE_ARK_VISION_BASE_URL.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        payload: dict[str, Any] = {
            "model": settings.VOLCENGINE_ARK_VISION_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_instruction},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        thinking_mode = settings.VOLCENGINE_ARK_VISION_THINKING_MODE.strip().lower()
        if thinking_mode in {"disabled", "enabled", "adaptive"}:
            payload["thinking"] = {"type": thinking_mode}
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
        choice = (data.get("choices") or [{}])[0]
        finish_reason = choice.get("finish_reason")
        usage = self._usage(data)
        if finish_reason == "length":
            raise VisionOutputLengthError(usage, finish_reason)
        content = (choice.get("message") or {}).get("content", "")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        try:
            raw_payload = _extract_json_object(str(content))
        except ValueError as exc:
            raise VisionStructuredOutputError(f"模型未返回完整 JSON：{exc}", usage, finish_reason) from exc
        parsed = _normalize_trade_payload(raw_payload) if trade_mode else _normalize_structured_payload(raw_payload)
        return parsed, finish_reason, usage

    def _request_with_length_retry(
        self,
        *,
        image_bytes: bytes,
        mime: str,
        prompt: str,
        user_instruction: str,
        max_tokens: int,
        trade_mode: bool,
    ) -> tuple[dict[str, Any], str | None, dict[str, int], bool]:
        try:
            parsed, finish_reason, usage = self._request(
                image_bytes=image_bytes,
                mime=mime,
                prompt=prompt,
                user_instruction=user_instruction,
                max_tokens=max_tokens,
                trade_mode=trade_mode,
            )
            return parsed, finish_reason, usage, False
        except (VisionOutputLengthError, VisionStructuredOutputError) as first_error:
            retry_budget = max(max_tokens, settings.VOLCENGINE_ARK_VISION_RETRY_MAX_TOKENS)
            if retry_budget <= max_tokens:
                raise first_error
            parsed, finish_reason, usage = self._request(
                image_bytes=image_bytes,
                mime=mime,
                prompt=prompt,
                user_instruction=user_instruction,
                max_tokens=retry_budget,
                trade_mode=trade_mode,
            )
            usage["attempts"] = 2
            return parsed, finish_reason, usage, True

    @staticmethod
    def _segment_holding_image(image_path: Path) -> list[bytes]:
        with Image.open(image_path) as image:
            image.load()
            width, height = image.size
            if height <= VISION_SEGMENT_HEIGHT:
                return [image_path.read_bytes()]
            result: list[bytes] = []
            top = 0
            while True:
                bottom = min(height, top + VISION_SEGMENT_HEIGHT)
                crop = image.crop((0, top, width, bottom))
                if crop.mode not in {"RGB", "L"}:
                    crop = crop.convert("RGB")
                output = BytesIO()
                crop.save(output, format="JPEG", quality=95, optimize=True)
                result.append(output.getvalue())
                if bottom >= height:
                    break
                top = bottom - VISION_SEGMENT_OVERLAP
            return result

    @staticmethod
    def _merge_segment_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
        merged_account = {key: None for key in (
            "total_assets", "cash_available", "total_market_value", "total_unrealized_pnl", "repo_amount", "repo_available_date",
        )}
        merged_rows: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for payload in payloads:
            for key, value in (payload.get("account_summary") or {}).items():
                if merged_account.get(key) is None and value is not None:
                    merged_account[key] = value
            for warning in payload.get("parse_warnings") or []:
                if warning and warning not in warnings:
                    warnings.append(str(warning))
            for row in payload.get("holdings") or []:
                symbol = str(row.get("raw_symbol") or "").strip()
                name = str(row.get("raw_name") or "").strip()
                key = symbol or name
                if not key:
                    continue
                existing = merged_rows.get(key)
                if existing is None:
                    merged_rows[key] = dict(row)
                    continue
                for field, value in row.items():
                    if existing.get(field) in (None, "", []) and value not in (None, "", []):
                        existing[field] = value
        return {
            "source_view": {"platform_guess": None, "screenshot_displayed_time": None, "warnings": []},
            "account_summary": merged_account,
            "holdings": list(merged_rows.values())[:MAX_HOLDING_ROWS],
            "unrecognized_text": [],
            "parse_warnings": warnings[:MAX_WARNING_ITEMS],
        }

    def _parse_holding_segments(self, image_path: Path) -> tuple[dict[str, Any], str | None, dict[str, int]]:
        segments = self._segment_holding_image(image_path)
        parsed_segments: list[dict[str, Any]] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "attempts": 0}
        for index, segment in enumerate(segments, start=1):
            instruction = (
                f"这是同一张持仓截图的第 {index}/{len(segments)} 段。"
                "仅提取当前图片中可见的持仓行，使用紧凑 JSON v3；"
                "只有第一段可填写账户摘要 a，其他段 a 必须全为 null。"
            )
            parsed, finish_reason, usage, retried = self._request_with_length_retry(
                image_bytes=segment,
                mime="image/jpeg",
                prompt=PORTFOLIO_VISION_COMPACT_PROMPT,
                user_instruction=instruction,
                max_tokens=settings.VOLCENGINE_ARK_VISION_SEGMENT_MAX_TOKENS,
                trade_mode=False,
            )
            parsed_segments.append(parsed)
            for key in total_usage:
                total_usage[key] += int(usage.get(key) or 0)
            if retried:
                total_usage["retry_segments"] = int(total_usage.get("retry_segments") or 0) + 1
        total_usage["segments"] = len(segments)
        return self._merge_segment_payloads(parsed_segments), finish_reason, total_usage

    def parse_image(self, image_path: Path, screenshot_kind: str = "current_holdings") -> OcrResult:
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
            mime = self._mime_for_path(image_path)
            trade_mode = screenshot_kind == "trade_history"
            prompt = TRADE_VISION_EXTRACTION_PROMPT if trade_mode else PORTFOLIO_VISION_COMPACT_PROMPT
            prompt_version = TRADE_VISION_PROMPT_VERSION if trade_mode else PORTFOLIO_VISION_PROMPT_VERSION
            user_instruction = (
                "提取这张成交截图中的全部交易行，只返回 JSON。"
                if trade_mode
                else "提取这张持仓截图中的账户摘要和全部持仓行，使用紧凑 JSON v3。"
            )
            used_segments = False
            try:
                parsed, finish_reason, usage, retried = self._request_with_length_retry(
                    image_bytes=image_bytes,
                    mime=mime,
                    prompt=prompt,
                    user_instruction=user_instruction,
                    max_tokens=settings.VOLCENGINE_ARK_VISION_MAX_TOKENS,
                    trade_mode=trade_mode,
                )
            except (VisionOutputLengthError, VisionStructuredOutputError):
                if trade_mode:
                    raise
                parsed, finish_reason, usage = self._parse_holding_segments(image_path)
                retried = True
                used_segments = True
            notices = ["云端视觉识别结果为待核对草稿，确认前不会写入正式账户快照。"]
            if used_segments:
                notices.append(f"完整截图两次输出超限，已自动分为 {usage.get('segments', 0)} 段识别并合并；请重点核对边界行。")
                prompt_version = PORTFOLIO_VISION_SEGMENT_PROMPT_VERSION
            elif retried:
                notices.append("首次输出超限或 JSON 格式不完整，已自动提高 token 上限重试并成功。")
            return OcrResult(
                provider_name=self.provider_name,
                status="draft_parsed",
                raw_text="[cloud vision structured JSON omitted]",
                warnings=notices,
                structured_payload=parsed,
                model_name=settings.VOLCENGINE_ARK_VISION_MODEL,
                prompt_version=prompt_version,
                finish_reason=finish_reason,
                usage=usage,
            )
        except requests.Timeout as exc:
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                raw_text="",
                warnings=[f"云端视觉识别超时，已转为可编辑草稿。当前超时阈值为 {settings.VOLCENGINE_ARK_VISION_TIMEOUT} 秒。"],
                error_summary=f"timeout after {settings.VOLCENGINE_ARK_VISION_TIMEOUT}s",
                model_name=settings.VOLCENGINE_ARK_VISION_MODEL,
            )
        except (VisionOutputLengthError, VisionStructuredOutputError) as exc:
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                raw_text="",
                warnings=["云端视觉识别在完整图和切片流程中均达到 token 上限，已转为可编辑草稿。"],
                error_summary=str(exc),
                model_name=settings.VOLCENGINE_ARK_VISION_MODEL,
                prompt_version=PORTFOLIO_VISION_SEGMENT_PROMPT_VERSION,
                finish_reason=exc.finish_reason,
                usage=exc.usage,
            )
        except Exception as exc:
            return OcrResult(
                provider_name=self.provider_name,
                status="cloud_parse_failed",
                raw_text="",
                warnings=[f"云端视觉识别失败，已转为可编辑草稿：{str(exc)[:300]}"],
                error_summary=str(exc)[:300],
                model_name=settings.VOLCENGINE_ARK_VISION_MODEL,
            )
