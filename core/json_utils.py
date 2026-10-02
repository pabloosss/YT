from __future__ import annotations

import json
import re


def strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def loads_relaxed(raw: str):
    text = strip_thinking(raw).strip()

    fence = "`" * 3
    if text.startswith(fence):
        text = re.sub(r"^\\s*`{3}(?:json)?\\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\\s*`{3}\\s*$", "", text, count=1)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    starts = [pos for pos in (text.find("["), text.find("{")) if pos >= 0]
    if not starts:
        raise ValueError("Model nie zwrócił JSON-u.")

    start = min(starts)
    if text[start] == "[":
        end = text.rfind("]")
    else:
        end = text.rfind("}")

    if end < start:
        raise ValueError("Model zwrócił niepełny JSON.")

    return json.loads(text[start:end + 1])
