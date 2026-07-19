"""Score Indonesian text sentiment in an isolated process.

Reads a JSON list of strings from stdin, prints a JSON list of
{"label", "score"} to stdout (aligned by index). Runs in a throwaway process so
torch RAM is reclaimed on exit and the always-on scheduler never imports torch.
Requires the ML extras (see requirements-ml.txt). Override the model with the
SENTIMENT_MODEL env var.
"""
import json
import os
import sys

DEFAULT_MODEL = "w11wo/indonesian-roberta-base-sentiment-classifier"


def main() -> int:
    texts = json.load(sys.stdin)
    if not texts:
        sys.stdout.write("[]")
        return 0
    from transformers import pipeline

    model = os.environ.get("SENTIMENT_MODEL", DEFAULT_MODEL)
    clf = pipeline("sentiment-analysis", model=model, truncation=True, max_length=256)
    results = clf([t[:1000] for t in texts])
    out = [{"label": r["label"], "score": float(r["score"])} for r in results]
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
