"""Safety guards: input sanitisation, prompt-injection detection and output grounding checks.

Defence in depth — none of these is the primary control. The primary controls are architectural:
identity comes only from the server-side ToolContext, tools enforce permissions/ownership, and every
write requires explicit confirmation. These guards add detection, logging and hallucination checks.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_MESSAGE_CHARS = 2000

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|all|your|system)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines)\b", re.I)),
    ("role_hijack", re.compile(r"\b(you are now|act as|pretend (to be|you are)|from now on you)\b.{0,40}\b(admin|administrator|developer|system|root|seller|dan|unrestricted)\b", re.I)),
    ("system_prompt_probe", re.compile(r"\b(reveal|show|print|repeat|what is)\b.{0,30}\b(system prompt|hidden (prompt|instructions)|your instructions|chain of thought)\b", re.I)),
    ("fake_system_tag", re.compile(r"(</?\s*(system|assistant|tool)\s*>|\[\s*system\s*\]|###\s*system)", re.I)),
    ("privilege_claim", re.compile(r"\b(i am (the|an) (admin|administrator|owner|developer)|admin (mode|override)|sudo|developer mode|jailbreak)\b", re.I)),
    ("tool_forcing", re.compile(r"\b(call|invoke|execute|run)\b.{0,20}\b(tool|function|update_price|delete|refund|set_price)\b", re.I)),
    ("data_exfiltration", re.compile(r"\b(all|every|other)\b.{0,20}\b(users?|customers?|sellers?|buyers?)\b.{0,30}\b(emails?|passwords?|addresses|orders|data|details)\b", re.I)),
]


@dataclass
class SafetyReport:
    text: str
    flags: list[str]
    truncated: bool

    @property
    def suspicious(self) -> bool:
        return bool(self.flags)

    @property
    def block(self) -> bool:
        """Requests that are purely attempts to exfiltrate data or hijack privileges are refused."""
        return any(f in ("data_exfiltration", "privilege_claim", "role_hijack") for f in self.flags)


def sanitize(text: str) -> tuple[str, bool]:
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text).strip()
    truncated = len(text) > MAX_MESSAGE_CHARS
    return text[:MAX_MESSAGE_CHARS], truncated


def inspect_message(raw: str) -> SafetyReport:
    text, truncated = sanitize(raw)
    flags = [name for name, rx in _INJECTION_PATTERNS if rx.search(text)]
    return SafetyReport(text, flags, truncated)


def wrap_untrusted(label: str, content: str) -> str:
    """Wrap retrieved/user content for LLM prompts so it is treated as data, not instructions."""
    content = content.replace("</data>", "&lt;/data&gt;")
    return f'<data source="{label}">\n{content}\n</data>'


_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


def money_mentions(text: str) -> list[str]:
    return [f"{float(m.replace(',', '')):.2f}" for m in _MONEY.findall(text)]


def grounding_violations(text: str, allowed_prices: set[str], user_text: str = "") -> list[str]:
    """Prices mentioned in generated text must come from tool results (or the user's own message)."""
    allowed = set(allowed_prices) | set(money_mentions(user_text))
    return [p for p in money_mentions(text) if p not in allowed]
