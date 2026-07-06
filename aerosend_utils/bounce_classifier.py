"""Classify raw SMTP bounce diagnostics into HARD / SOFT / BLOCK."""

import re

BLOCK_PATTERNS = [
    r"spamhaus", r"blocked", r"blacklist", r"listed at", r"reputation", r"5\.7\.1",
]
HARD_PATTERNS = [
    r"5\.1\.1", r"user unknown", r"no such user", r"mailbox not found", r"does not exist", r"5\.1\.10",
]


def classify(smtp_code: int, diagnostic: str) -> str:
    text = diagnostic.lower()
    if any(re.search(p, text) for p in BLOCK_PATTERNS):
        return "BLOCK"
    if smtp_code >= 500 and any(re.search(p, text) for p in HARD_PATTERNS):
        return "HARD"
    if smtp_code >= 500:
        return "HARD"
    return "SOFT"
