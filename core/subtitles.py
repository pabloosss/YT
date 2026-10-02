from __future__ import annotations

import re
from pathlib import Path


def clean_narration(text: str) -> str:
    """Turn an agent's Markdown answer into text suitable for a narrator."""
    value = re.sub(r"<think>.*?</think>", " ", text, flags=re.I | re.S)
    value = re.sub(r"(?m)^\s*#{1,6}\s*", "", value)
    value = re.sub(r"(?m)^\s*[-*]\s+", "", value)
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\*(.*?)\*", r"\1", value)
    value = re.sub(r"\[(?:\d+(?:\s*[-,]\s*\d+)*)\]", "", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"(?mi)^\s*(hook|rozwinięcie|rozwój|finał|podsumowanie)\s*:\s*", "", value)
    value = re.split(r"(?mi)^\s*---\s*$", value, maxsplit=1)[0]
    value = re.sub(r"\s+", " ", value).strip()
    return value


def short_narration(text: str, *, max_words: int = 60, max_characters: int = 550) -> str:
    """Keep paid TTS input within the length of a 30-second Short."""
    selected: list[str] = []
    for word in clean_narration(text).split():
        candidate = " ".join([*selected, word])
        if len(selected) >= max_words or len(candidate) > max_characters:
            break
        selected.append(word)
    value = " ".join(selected).strip()
    if value and value[-1] not in ".!?…":
        value = value.rstrip(",;:–—-") + "."
    return value


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def alignment_to_srt(alignment: dict, output: Path, *, words_per_caption: int = 4) -> Path:
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not chars or not (len(chars) == len(starts) == len(ends)):
        raise ValueError("ElevenLabs nie zwrócił prawidłowych znaczników czasu.")

    words: list[tuple[str, float, float]] = []
    index = 0
    while index < len(chars):
        while index < len(chars) and str(chars[index]).isspace():
            index += 1
        if index >= len(chars):
            break
        begin = index
        while index < len(chars) and not str(chars[index]).isspace():
            index += 1
        word = "".join(str(item) for item in chars[begin:index]).strip()
        if word:
            words.append((word, float(starts[begin]), float(ends[index - 1])))

    captions: list[tuple[str, float, float]] = []
    current: list[tuple[str, float, float]] = []
    for word in words:
        current.append(word)
        text = " ".join(item[0] for item in current)
        sentence_end = bool(re.search(r"[.!?…][\"”']?$", word[0]))
        if len(current) >= words_per_caption or len(text) >= 28 or sentence_end:
            captions.append((text, current[0][1], current[-1][2]))
            current = []
    if current:
        captions.append((" ".join(item[0] for item in current), current[0][1], current[-1][2]))

    output.parent.mkdir(parents=True, exist_ok=True)
    blocks = [
        f"{number}\n{_srt_time(start)} --> {_srt_time(max(end, start + 0.15))}\n{text}"
        for number, (text, start, end) in enumerate(captions, start=1)
    ]
    output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return output


def text_to_srt(text: str, output: Path, *, duration_seconds: float = 30.0,
                words_per_caption: int = 4) -> Path:
    """Create approximate captions locally when narration exists but timestamps do not."""
    words = clean_narration(text).split()
    if not words:
        raise ValueError("Scenariusz nie zawiera tekstu do utworzenia napisów.")
    chunks = [words[index:index + words_per_caption] for index in range(0, len(words), words_per_caption)]
    seconds_per_word = duration_seconds / len(words)
    blocks = []
    word_index = 0
    for number, chunk in enumerate(chunks, start=1):
        start = word_index * seconds_per_word
        word_index += len(chunk)
        end = min(duration_seconds, word_index * seconds_per_word)
        blocks.append(
            f"{number}\n{_srt_time(start)} --> {_srt_time(max(end, start + 0.15))}\n{' '.join(chunk)}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return output
