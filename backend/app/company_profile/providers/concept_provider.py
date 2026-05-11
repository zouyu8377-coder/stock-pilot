import json
from pathlib import Path

CONCEPTS_PATH = Path(__file__).resolve().parents[3] / "data" / "concepts" / "concepts.json"


class ConceptProvider:
    """
    本地静态概念标签系统。
    从 JSON 文件按公司名称映射概念标签。
    """

    def __init__(self):
        self._concepts: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if CONCEPTS_PATH.exists():
                with open(CONCEPTS_PATH, "r", encoding="utf-8") as f:
                    self._concepts = json.load(f)
        except Exception as e:
            print(f"[ConceptProvider] load failed: {e}")
            self._concepts = {}

    def get_concepts(self, company_name: str) -> list[str]:
        return self._concepts.get(company_name, [])

    def get_all_names(self) -> list[str]:
        return list(self._concepts.keys())
