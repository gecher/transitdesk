import re
from pathlib import Path

from rank_bm25 import BM25Okapi

STOPWORDS = {"a", "an", "the", "is", "are", "i", "my", "me", "do", "can", "if", "to", "of",
             "for", "and", "or", "in", "on", "at", "it", "be", "what", "how", "get", "will"}


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


def load_sections(path: str = "policies.md") -> list[str]:
    text = Path(__file__).with_name(path).read_text(encoding="utf-8")
    return ["## " + part.strip() for part in text.split("\n## ")[1:]]   # one chunk per section


SECTIONS = load_sections()
BM25 = BM25Okapi([tokenize(s) for s in SECTIONS])


def search(query: str, k: int = 2) -> list[str]:
    scores = BM25.get_scores(tokenize(query))
    ranked = sorted(zip(scores, SECTIONS), key=lambda pair: pair[0], reverse=True)
    return [section for score, section in ranked[:k] if score > 0]


if __name__ == "__main__":
    for q in ["free hotel connection 10 hours", "stuck between flights overnight room"]:
        print(f"\n{q}")
        for s in search(q):
            print("  ->", s.splitlines()[0])