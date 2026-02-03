#!/usr/bin/env python3
"""
Update STT phrase hints from transcript logs.

Reads transcript sources (json/jsonl/plain text) and merges extracted
proper-noun candidates into a phrase list file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple


try:
    from kiwipiepy import Kiwi

    KIWI_AVAILABLE = True
except Exception:
    KIWI_AVAILABLE = False


DEFAULT_KEYS = ("transcript", "text", "utterance")


def _load_existing_phrases(path: str) -> List[str]:
    if not os.path.exists(path):
        return []

    phrases: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            phrase = line.strip()
            if phrase and not phrase.startswith("#"):
                phrases.append(phrase)
    return phrases


def _extract_from_text(text: str, kiwi: Optional["Kiwi"], min_length: int) -> List[str]:
    candidates: List[str] = []

    if kiwi is not None:
        for token in kiwi.tokenize(text):
            if token.tag in ("NNP", "SL"):
                if len(token.form) >= min_length:
                    candidates.append(token.form)
        return candidates

    for token in re.findall(r"[A-Za-z][A-Za-z0-9._-]{1,}", text):
        if len(token) >= min_length:
            candidates.append(token)
    return candidates


def _extract_texts_from_object(obj: object) -> Iterable[str]:
    if isinstance(obj, dict):
        for key in DEFAULT_KEYS:
            if key in obj:
                value = obj[key]
                if value:
                    yield str(value)
                return
    elif isinstance(obj, list):
        for item in obj:
            yield from _extract_texts_from_object(item)


def _read_texts(path: str) -> Iterable[str]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        obj = json.loads(content)
        yield from _extract_texts_from_object(obj)
        return
    except Exception:
        pass

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            found = False
            if isinstance(obj, dict):
                for key in DEFAULT_KEYS:
                    if key in obj:
                        value = obj.get(key)
                        if value:
                            yield str(value)
                            found = True
                            break
            if found:
                continue
        except Exception:
            pass
        yield line


def _collect_candidates(paths: List[str], min_length: int) -> Counter:
    kiwi = Kiwi() if KIWI_AVAILABLE else None
    counts: Counter = Counter()

    for path in paths:
        for text in _read_texts(path):
            for candidate in _extract_from_text(text, kiwi, min_length):
                counts[candidate] += 1

    return counts


def _merge_phrases(
    existing: List[str],
    counts: Counter,
    min_count: int,
    top: Optional[int],
) -> Tuple[List[str], List[str]]:
    existing_set = set(existing)
    candidates = [
        phrase
        for phrase, count in counts.most_common()
        if count >= min_count and phrase not in existing_set
    ]

    if top is not None:
        candidates = candidates[:top]

    updated = existing + candidates
    return updated, candidates


def _write_phrases(path: str, phrases: List[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for phrase in phrases:
            f.write(phrase + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Update STT phrase list")
    parser.add_argument("inputs", nargs="+", help="Transcript source files")
    parser.add_argument(
        "--output",
        default=os.getenv("AICC_STT_PHRASES_PATH", "phrases.txt"),
        help="Output phrase list path",
    )
    parser.add_argument("--min-length", type=int, default=2)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    existing = _load_existing_phrases(args.output)
    counts = _collect_candidates(args.inputs, args.min_length)
    updated, added = _merge_phrases(existing, counts, args.min_count, args.top)

    if args.dry_run:
        print(f"existing={len(existing)} added={len(added)} total={len(updated)}")
        for phrase in added:
            print(phrase)
        return 0

    _write_phrases(args.output, updated)
    print(f"updated={args.output} added={len(added)} total={len(updated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
