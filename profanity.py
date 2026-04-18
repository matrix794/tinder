# -*- coding: utf-8 -*-
"""
Фильтр ненормативной лексики (русский + типичные латинские «обходы»).
Расширение: файл profanity_words_ru.txt рядом с этим модулем (по одному корню/слову в строке).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

# Минимальная длина «корня» — 3 символа, чтобы не ловить «хлеб», «художник» и т.п.
_DEFAULT_LINES = """
хуй
хуя
хуе
хуи
хуё
хер
пизд
ебан
ебёт
ебет
ебал
ебут
ебар
ебуч
ёбан
бляд
блят
сука
сукин
муда
гандон
гондон
пидор
пидр
мраз
сволоч
ублюд
залуп
мандав
долбо
долба
гнида
шлюх
хуило
похуй
охуе
ахуе
нахуй
похер
чмо
чмы
"""

# Латинские буквы, похожие на кириллицу (для обходов вроде xyu / huj)
_LATIN_LOOKALIKE = str.maketrans(
    {
        "a": "а",
        "b": "в",
        "c": "с",
        "e": "е",
        "f": "ф",
        "g": "д",
        "h": "н",
        "i": "и",
        "k": "к",
        "l": "л",
        "m": "м",
        "n": "п",
        "o": "о",
        "p": "р",
        "r": "г",
        "s": "с",
        "t": "т",
        "u": "у",
        "v": "м",
        "x": "х",
        "y": "у",
        "z": "з",
    }
)


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = text.lower().replace("ё", "е")
    t = t.replace("@", "а").replace("0", "о").replace("3", "з").replace("4", "ч")
    t = re.sub(r"[_*·•]+", " ", t)
    # смешанная латиница
    t = t.translate(_LATIN_LOOKALIKE)
    t = re.sub(r"[^а-яa-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


@lru_cache(maxsize=1)
def _bad_substrings() -> frozenset[str]:
    words: set[str] = set()
    for raw in _DEFAULT_LINES.splitlines():
        w = raw.strip().lower()
        if not w or w.startswith("#"):
            continue
        if len(w) >= 3:
            words.add(w)
    path = os.path.join(os.path.dirname(__file__), "profanity_words_ru.txt")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if not w or w.startswith("#"):
                    continue
                if len(w) >= 3:
                    words.add(w)
    return frozenset(words)


def contains_profanity(text: str | None) -> bool:
    """True, если в тексте есть запрещённые слова/корни."""
    if not text or not str(text).strip():
        return False
    norm = _normalize(str(text))
    if not norm:
        return False
    compact = norm.replace(" ", "")
    bad = _bad_substrings()
    for w in norm.split():
        for b in bad:
            if b in w:
                return True
    for b in bad:
        if b in compact:
            return True
    return False
