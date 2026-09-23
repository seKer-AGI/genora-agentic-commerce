"""Catalog-aware entity matching (categories, brands) driven by hints supplied by the host application."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Domain vocabulary per category slug. Only slugs present in the live catalog are used.
CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "laptops": ("laptop", "laptops", "notebook computer", "chromebook", "ultrabook", "macbook"),
    "smartphones": ("phone", "phones", "smartphone", "smartphones", "mobile phone", "cell phone"),
    "audio": ("headphones", "headphone", "earbuds", "earphones", "headset", "speaker", "speakers", "soundbar"),
    "cameras": ("camera", "cameras", "mirrorless", "dslr", "action cam", "action camera"),
    "camera-accessories": ("lens", "lenses", "tripod", "sd card", "memory card", "camera bag", "camera battery"),
    "wearables": ("smartwatch", "smart watch", "watch", "fitness tracker", "fitness band", "running watch"),
    "computer-accessories": ("keyboard", "mouse", "monitor", "usb hub", "usb-c hub", "dock", "docking station"),
    "running-shoes": ("running shoes", "running shoe", "sneakers", "trainers", "runners", "trail shoes", "shoes"),
    "outerwear": ("jacket", "jackets", "coat", "parka", "fleece", "rain jacket", "raincoat"),
    "bags": ("backpack", "backpacks", "bag", "bags", "duffel", "laptop sleeve", "rucksack"),
    "kitchen-appliances": ("espresso machine", "coffee machine", "coffee maker", "blender", "air fryer", "kettle",
                           "multicooker", "pressure cooker", "knife set", "knives"),
    "furniture": ("desk", "standing desk", "office chair", "chair", "bookshelf", "monitor riser"),
    "fitness": ("dumbbells", "yoga mat", "yoga", "resistance bands", "foam roller", "home gym"),
    "camping": ("tent", "sleeping bag", "headlamp", "camping", "cook kit"),
    "beauty": ("serum", "sunscreen", "spf", "moisturizer", "moisturiser", "cleanser", "skincare", "skin care"),
    "books": ("book", "books", "paper notebook", "journal", "pens", "stationery"),
    "toys": ("board game", "puzzle", "jigsaw", "toy", "toys", "stem kit", "trivia"),
}


@dataclass
class CategoryMatch:
    slug: str
    name: str
    matched: str


class CatalogMatcher:
    def __init__(self, hints: dict[str, Any]) -> None:
        cats = hints.get("categories", [])
        self.categories = {c["slug"]: c for c in cats}
        self.brands: list[str] = sorted(hints.get("brands", []), key=len, reverse=True)
        phrases: list[tuple[str, str]] = []
        for slug, cat in self.categories.items():
            phrases.append((cat["name"].lower(), slug))
            for syn in CATEGORY_SYNONYMS.get(slug, ()):
                phrases.append((syn, slug))
        # longest phrases first so "rain jacket" beats "jacket", "running shoes" beats "shoes"
        self._phrases = sorted(phrases, key=lambda p: len(p[0]), reverse=True)

    def category(self, text: str) -> CategoryMatch | None:
        low = text.lower()
        for phrase, slug in self._phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", low):
                return CategoryMatch(slug, self.categories[slug]["name"], phrase)
        return None

    def brand(self, text: str) -> str | None:
        low = text.lower()
        for b in self.brands:
            if re.search(rf"\b{re.escape(b.lower())}\b", low):
                return b
        return None

    def category_name(self, slug: str | None) -> str | None:
        return self.categories.get(slug, {}).get("name") if slug else None

    def top_categories(self, n: int = 6) -> list[str]:
        roots = [c["name"] for c in self.categories.values() if not c.get("parent_slug")]
        return roots[:n]
