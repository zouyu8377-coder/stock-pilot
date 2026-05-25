from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OcrResult:
    provider_name: str
    status: str
    raw_text: str = ""
    warnings: list[str] | None = None


class LocalOcrProvider:
    provider_name = "local_noop"

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
            warnings=[
                "当前环境未配置可靠的本地 OCR 引擎；已保留截图并创建可手工补录的草稿。",
            ],
        )

