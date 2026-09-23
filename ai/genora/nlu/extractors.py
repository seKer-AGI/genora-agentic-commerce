"""Deterministic slot extractors (budget, price, quantity, references, product phrases, attributes)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_NUM = r"\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d{1,2})?)\s?(k\b)?"


def _to_num(raw: str, k: str | None = None) -> Decimal:
    value = Decimal(raw.replace(",", ""))
    return value * 1000 if k else value


@dataclass
class Budget:
    min: Decimal | None = None
    max: Decimal | None = None

    @property
    def empty(self) -> bool:
        return self.min is None and self.max is None


_BUDGET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"between\s+{_NUM}\s+(?:and|-|to)\s+{_NUM}", re.I), "range"),
    (re.compile(rf"{_NUM}\s*(?:-|to)\s*{_NUM}", re.I), "range"),
    (re.compile(rf"(?:under|below|less than|max(?:imum)?|up to|no more than|at most|cheaper than|within|<)\s*{_NUM}", re.I), "max"),
    (re.compile(rf"(?:over|above|more than|at least|min(?:imum)?|>)\s*{_NUM}", re.I), "min"),
    (re.compile(rf"(?:around|about|roughly|approx(?:imately)?|~)\s*{_NUM}", re.I), "around"),
    (re.compile(rf"budget(?:\s+is|\s+of|:)?\s*{_NUM}", re.I), "max"),
    (re.compile(rf"{_NUM}\s*(?:budget|max|or less|tops)", re.I), "max"),
]
_BARE_MONEY = re.compile(r"(?:^|\s)\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d{1,2})?)\s?(k\b)?", re.I)
_ONLY_NUMBER = re.compile(r"^\s*(?:it'?s|about|around|my budget is|budget)?\s*\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d{1,2})?)\s?(k)?\s*(?:dollars|usd|bucks)?\s*[.!]?\s*$", re.I)
NO_BUDGET = re.compile(r"\b(no budget|any budget|doesn'?t matter|don'?t care|no limit|whatever|not sure|skip)\b", re.I)


def extract_budget(text: str, *, allow_bare_number: bool = False) -> Budget:
    for rx, kind in _BUDGET_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        g = m.groups()
        if kind == "range":
            a, b = _to_num(g[0], g[1]), _to_num(g[2], g[3])
            return Budget(min(a, b), max(a, b))
        v = _to_num(g[0], g[1])
        if kind == "max":
            return Budget(None, v)
        if kind == "min":
            return Budget(v, None)
        return Budget((v * Decimal("0.85")).quantize(Decimal(1)), (v * Decimal("1.15")).quantize(Decimal(1)))
    if allow_bare_number:
        m = _ONLY_NUMBER.match(text) or _BARE_MONEY.search(text)
        if m:
            return Budget(None, _to_num(m.group(1), m.group(2)))
    return Budget()


_OFFER = re.compile(
    rf"(?:for|at|pay|offer(?:ing)?|give you|take|do|get it for|accept)\s*{_NUM}", re.I)


def extract_offer_price(text: str) -> Decimal | None:
    m = _OFFER.search(text) or _BARE_MONEY.search(text)
    return _to_num(m.group(1), m.group(2)) if m else None


_QTY = re.compile(r"\b(\d{1,2})\s*(?:x\b|units?|pcs|pieces|of (?:them|these|those|it))", re.I)
_WORD_QTY = {"two": 2, "three": 3, "four": 4, "five": 5, "a couple of": 2, "a pair of": 2}


def extract_quantity(text: str) -> int | None:
    m = _QTY.search(text)
    if m:
        return int(m.group(1))
    low = text.lower()
    for word, n in _WORD_QTY.items():
        if re.search(rf"\b{word}\b", low):
            return n
    return None


ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3,
            "fifth": 4, "5th": 4, "last": -1}
_ORDINAL_RX = re.compile(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\b(?:\s+(?:one|item|product|option))?", re.I)
_HASH_RX = re.compile(r"(?:#|number|no\.?|option)\s*(\d)\b", re.I)
_PRONOUN_RX = re.compile(r"\b(it|this|that|this one|that one|the one|them|these|those)\b", re.I)
_TOP_N = re.compile(r"\b(?:these|those|the|top)\s+(two|three|four|five|2|3|4|5)\b", re.I)
_N_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}


def extract_ordinals(text: str) -> list[int]:
    idx = [ORDINALS[m.group(1).lower()] for m in _ORDINAL_RX.finditer(text)]
    idx += [int(m.group(1)) - 1 for m in _HASH_RX.finditer(text)]
    seen: list[int] = []
    for i in idx:
        if i not in seen:
            seen.append(i)
    return seen


def extract_top_n(text: str) -> int | None:
    m = _TOP_N.search(text)
    if not m:
        return None
    v = m.group(1).lower()
    return _N_WORDS.get(v) or int(v)


def mentions_reference(text: str) -> bool:
    return bool(_PRONOUN_RX.search(text) or _ORDINAL_RX.search(text) or _HASH_RX.search(text))


# Phrases that introduce a product name, e.g. "reviews for the Quiet 900", "compare X and Y".
_LEADS = re.compile(
    r"(?:about|for|on|of|with|compare|comparing|between|is|are|the|buy|get|add|price of|reviews? (?:of|for))\s+"
    r"(?:the\s+|this\s+|that\s+|a\s+|an\s+|my\s+)?(.+)$",
    re.I,
)
_TRAILING = re.compile(
    r"\s*(?:\?|\.|!|,)?\s*(?:please|thanks|any good|worth it|on other (?:sites|marketplaces|stores)|elsewhere|"
    r"to (?:my|the) cart|for \$?\d.*|at \$?\d.*)?\s*$", re.I)
_FILLER = re.compile(r"^(?:the|this|that|these|those|a|an|my|it|them)\b\s*", re.I)


def product_phrase(text: str) -> str | None:
    """Best-effort product name phrase from a sentence (used to resolve against the catalog)."""
    m = _LEADS.search(text)
    phrase = m.group(1) if m else text
    phrase = _TRAILING.sub("", phrase).strip(" ?.!,'\"")
    phrase = _FILLER.sub("", phrase).strip()
    if len(phrase) < 3 or phrase.lower() in {"it", "one", "this one", "that one", "them", "product", "item"}:
        return None
    return phrase[:120]


def split_compare_targets(text: str) -> list[str]:
    body = re.sub(r"^.*?\b(?:compare|comparing|between|difference between)\b", "", text, flags=re.I).strip()
    parts = re.split(r"\s*(?:,|\bvs\.?\b|\bversus\b|\band\b|\bor\b|&)\s*", body, flags=re.I)
    cleaned = [_FILLER.sub("", p.strip(" ?.!")).strip() for p in parts]
    return [p for p in cleaned if len(p) >= 3 and p.lower() not in {"them", "these", "those", "it"}]


# Attribute requirements expressed in natural language → structured constraints.
_ATTR_RULES: list[tuple[re.Pattern[str], str, str, float | str | bool]] = [
    (re.compile(r"(\d{1,3})\s?gb\s?(?:of\s)?ram", re.I), "ram_gb", "min", 0),
    (re.compile(r"(\d{3,4})\s?gb\s?(?:ssd|storage)", re.I), "storage_gb", "min", 0),
    (re.compile(r"(\d)\s?tb\b", re.I), "storage_gb", "min_tb", 0),
    (re.compile(r"\b(light(?:weight)?|portable|ultralight)\b", re.I), "weight_kg", "max", 1.6),
    (re.compile(r"\b(long battery|all[- ]day battery|battery life)\b", re.I), "battery_hours", "min", 10),
    (re.compile(r"\b(waterproof|water[- ]resistant)\b", re.I), "waterproof", "flag", True),
    (re.compile(r"\b(noise[- ]cancell?(?:ing|ation)|anc)\b", re.I), "anc", "flag", True),
    (re.compile(r"\b(gps)\b", re.I), "gps", "flag", True),
]


def extract_attribute_constraints(text: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for rx, attr, op, default in _ATTR_RULES:
        m = rx.search(text)
        if not m:
            continue
        if op == "min":
            value: object = float(m.group(1)) if default == 0 else default
            out.append({"attribute": attr, "op": ">=", "value": value})
        elif op == "min_tb":
            out.append({"attribute": attr, "op": ">=", "value": float(m.group(1)) * 1024})
        elif op == "max":
            out.append({"attribute": attr, "op": "<=", "value": default})
        else:
            out.append({"attribute": attr, "op": "==", "value": default})
    return out


USE_CASES = {
    "programming": ("programming", "coding", "developer", "software", "code", "dev work", "compiling"),
    "gaming": ("gaming", "games", "gamer", "esports"),
    "student": ("student", "school", "college", "university", "studying", "homework"),
    "travel": ("travel", "travelling", "traveling", "commute", "flights", "on the go"),
    "creator": ("video editing", "editing", "content creation", "creator", "photography", "vlogging", "youtube"),
    "business": ("business", "office", "work", "meetings"),
    "running": ("running", "marathon", "jogging", "5k", "10k", "race"),
    "hiking": ("hiking", "trail", "trekking", "camping", "outdoors"),
    "fitness": ("gym", "workout", "fitness", "training", "yoga"),
}


def extract_use_cases(text: str) -> list[str]:
    low = text.lower()
    return [uc for uc, keys in USE_CASES.items() if any(re.search(rf"\b{re.escape(k)}\b", low) for k in keys)]
