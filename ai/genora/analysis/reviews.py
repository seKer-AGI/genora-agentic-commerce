"""Extractive, lexicon-based review analysis.

Produces themes with positive/negative mention counts and verbatim supporting snippets taken from the
reviews themselves. It never invents claims: every theme is backed by at least one quoted snippet.
An LLM may optionally rephrase the resulting summary (see Nova's review workflow), but only on top of
these extracted facts.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

THEMES: dict[str, tuple[str, ...]] = {
    "Battery life": ("battery", "charge", "charger", "drains", "hours of"),
    "Build quality": ("build", "premium", "sturdy", "flimsy", "well built", "quality", "stitching", "zipper", "broke", "scratch"),
    "Performance": ("performance", "fast", "snappy", "slow", "lag", "warm under load", "heats"),
    "Display": ("screen", "display", "bright", "sharp"),
    "Sound": ("sound", "audio", "bass", "noise cancel"),
    "Noise": ("fan noise", "louder", "noisy", "quiet"),
    "Comfort & fit": ("comfortable", "comfort", "fit", "fits", "size", "sizing", "stiff", "grip", "support"),
    "Value for money": ("value", "price", "worth", "expensive", "for the price"),
    "Ease of use & setup": ("setup", "easy", "instructions", "assembly", "learn", "confusing"),
    "Durability": ("durable", "held up", "broke after", "lasted", "one part broke"),
    "Weight & portability": ("lightweight", "light", "heavier", "packs small", "carry", "bulky"),
    "Shipping & packaging": ("arrived", "packaging", "box", "damaged", "shipping", "missing a piece"),
    "Customer support": ("support was", "customer support", "service"),
    "Software": ("software", "bugs", "app"),
    "Skin feel & results": ("hydrated", "irritation", "absorbs", "broke me out", "gentle", "effective", "scent"),
    "Cleaning & maintenance": ("clean", "cleaning"),
    "Appearance": ("looks", "colour", "color", "photos", "fingerprints"),
}

_NEG_MARKERS = re.compile(
    r"\b(not|no|never|disappoint\w*|complaint|but|however|issue|problem|broke|poor|bad|worse|flimsy|drains|"
    r"louder|confusing|damaged|missing|stiff|bulky|slow|bugs|too|smaller|off|loose|weak|scratch)\b",
    re.IGNORECASE,
)
_POS_MARKERS = re.compile(
    r"\b(great|excellent|love|premium|comfortable|easy|sturdy|worth|recommend|perfect|fast|snappy|bright|sharp|"
    r"rich|durable|gentle|effective|lightweight|quickly|hydrated|fun|beautiful|clear)\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?])\s+|\s*(?:,\s*but\s+|;\s*|\bOnly complaint:\s*)", re.IGNORECASE)


@dataclass
class ReviewInput:
    rating: int
    title: str | None
    body: str
    verified: bool = True


@dataclass
class Theme:
    name: str
    positive: int = 0
    negative: int = 0
    snippets_positive: list[str] = field(default_factory=list)
    snippets_negative: list[str] = field(default_factory=list)

    @property
    def mentions(self) -> int:
        return self.positive + self.negative

    def as_dict(self) -> dict[str, object]:
        return {
            "theme": self.name, "mentions": self.mentions, "positive": self.positive, "negative": self.negative,
            "sentiment": "positive" if self.positive > self.negative * 1.5 else
                         "negative" if self.negative > self.positive * 1.5 else "mixed",
            "examples_positive": self.snippets_positive[:2], "examples_negative": self.snippets_negative[:2],
        }


@dataclass
class ReviewInsights:
    review_count: int
    average_rating: float
    distribution: dict[str, int]
    verified_share: float
    themes: list[Theme]
    top_positive: list[str]
    top_negative: list[str]
    summary: str
    method: str = "extractive-lexicon-v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "review_count": self.review_count, "average_rating": self.average_rating,
            "distribution": self.distribution, "verified_share": self.verified_share,
            "themes": [t.as_dict() for t in self.themes], "top_positive": self.top_positive,
            "top_negative": self.top_negative, "summary": self.summary, "method": self.method,
        }


def _clause_polarity(clause: str, rating: int) -> int:
    neg = len(_NEG_MARKERS.findall(clause))
    pos = len(_POS_MARKERS.findall(clause))
    if neg > pos:
        return -1
    if pos > neg:
        return 1
    return 1 if rating >= 4 else -1 if rating <= 2 else 0


def analyze_reviews(reviews: Sequence[ReviewInput], max_themes: int = 6) -> ReviewInsights:
    dist = {str(i): 0 for i in range(1, 6)}
    themes: dict[str, Theme] = {}
    for r in reviews:
        dist[str(r.rating)] += 1
        text = f"{r.body}"
        for raw in _CLAUSE_SPLIT.split(text):
            clause = raw.strip(" .!").strip()
            if len(clause) < 6:
                continue
            low = clause.lower()
            polarity = _clause_polarity(clause, r.rating)
            for theme, keys in THEMES.items():
                if any(k in low for k in keys):
                    t = themes.setdefault(theme, Theme(theme))
                    snippet = clause[:140]
                    if polarity > 0:
                        t.positive += 1
                        if snippet not in t.snippets_positive:
                            t.snippets_positive.append(snippet)
                    elif polarity < 0:
                        t.negative += 1
                        if snippet not in t.snippets_negative:
                            t.snippets_negative.append(snippet)
                    break
    n = len(reviews)
    avg = round(sum(r.rating for r in reviews) / n, 2) if n else 0.0
    ranked = sorted(themes.values(), key=lambda t: t.mentions, reverse=True)[:max_themes]
    top_pos = [t.name for t in sorted(ranked, key=lambda t: t.positive, reverse=True) if t.positive > t.negative][:3]
    top_neg = [t.name for t in sorted(ranked, key=lambda t: t.negative, reverse=True) if t.negative >= max(1, t.positive // 2)][:3]
    return ReviewInsights(
        review_count=n, average_rating=avg, distribution=dist,
        verified_share=round(sum(1 for r in reviews if r.verified) / n, 2) if n else 0.0,
        themes=ranked, top_positive=top_pos, top_negative=top_neg, summary=_summarize(n, avg, dist, top_pos, top_neg),
    )


def _summarize(n: int, avg: float, dist: dict[str, int], pos: list[str], neg: list[str]) -> str:
    if n == 0:
        return "There are no published reviews for this product yet."
    share_pos = round(100 * (dist["4"] + dist["5"]) / n)
    parts = [f"Based on {n} review{'s' if n != 1 else ''} (average {avg}/5), {share_pos}% of reviewers rated it 4 stars or higher."]
    if pos:
        parts.append("Reviewers most often praise: " + ", ".join(p.lower() for p in pos) + ".")
    if neg:
        parts.append("Common complaints concern: " + ", ".join(p.lower() for p in neg) + ".")
    if n < 5:
        parts.append("With few reviews, these trends may not be representative.")
    return " ".join(parts)


def keyword_counts(reviews: Sequence[ReviewInput]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for r in reviews:
        low = r.body.lower()
        for theme, keys in THEMES.items():
            if any(k in low for k in keys):
                counts[theme] += 1
    return counts


def group_by_rating(reviews: Sequence[ReviewInput]) -> dict[int, list[ReviewInput]]:
    out: dict[int, list[ReviewInput]] = defaultdict(list)
    for r in reviews:
        out[r.rating].append(r)
    return out
