import json
import os
from typing import Any, List

class Exporter:
    def __init__(self, logger=None):
        self.log = logger

    def to_json(self, data: List[Any], path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if self.log:
            self.log.info(f"Wrote JSON to {path}")