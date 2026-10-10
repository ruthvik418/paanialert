"""Score field extraction on data/test_messages.jsonl. Owner: B.

    python scripts/eval_extraction.py                       # keyword fallback, no AWS needed
    python scripts/eval_extraction.py --method agent        # the live bot's path (needs the paani profile)
    python scripts/eval_extraction.py --method structured   # agent/extract.py: one structured-output call
    python scripts/eval_extraction.py --method agent --write   # also save docs/eval.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FIELDS = ("smell", "colour", "taste", "since_days", "sick_count")


def load() -> list[dict]:
    with open(ROOT / "data" / "test_messages.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def extractor(method: str):
    if method == "fallback":
        from agent.fallback import extract
        return lambda text: extract(text)
    os.environ.setdefault("AWS_PROFILE", "paani")
    if method == "structured":
        from agent.extract import extract
        return lambda text: extract(text).model_dump()
    return _live_agent()


def _live_agent():
    """What the WhatsApp bot does: runner.reply, i.e. forced extraction with the model fallback chain.
    The save is captured instead of written, so nothing reaches DynamoDB."""
    from types import SimpleNamespace

    import agent.runner as runner
    from agent.reports import TurnContext

    def capture(ctx, fields, extracted_by):
        ctx.saved = SimpleNamespace(lat=None, fields=fields, extracted_by=extracted_by)
        return ctx.saved

    runner.save_extracted = capture

    def run(text: str) -> dict:
        ctx = TurnContext(phone_hash="eval", lang="en", text=text)
        try:
            runner.reply(text, ctx, [])
        except runner.AgentUnavailable:
            return {"saved_by": "no model (keywords in production)"}
        if not ctx.saved:
            return {"saved_by": "not saved"}
        return {**ctx.saved.fields, "saved_by": ctx.saved.extracted_by}
    return run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["fallback", "agent", "structured"], default="fallback")
    parser.add_argument("--write", action="store_true", help="save the results to docs/eval.md")
    args = parser.parse_args()

    run = extractor(args.method)
    rows = load()
    correct = {f: 0 for f in FIELDS}
    all_right = 0
    misses = []
    saved_by: dict[str, int] = {}
    for row in rows:
        got = run(row["text"])
        if "saved_by" in got:
            saved_by[got["saved_by"]] = saved_by.get(got["saved_by"], 0) + 1
        wrong = [f for f in FIELDS if got.get(f) != row["expected"][f]]
        for f in FIELDS:
            correct[f] += f not in wrong
        all_right += not wrong
        if wrong:
            misses.append((row, got, wrong))

    n = len(rows)
    lines = [
        f"# Extraction accuracy ({args.method})",
        "",
        f"Run {time.strftime('%Y-%m-%d %H:%M')} on {n} labelled messages (`data/test_messages.jsonl`).",
        "",
        "| Field | Correct | Accuracy |",
        "|---|---|---|",
        *[f"| {f} | {correct[f]}/{n} | {correct[f] / n:.0%} |" for f in FIELDS],
        f"| **All five fields right** | **{all_right}/{n}** | **{all_right / n:.0%}** |",
        "",
        *([f"Saved by: {', '.join(f'{k} {v}' for k, v in sorted(saved_by.items()))}.", ""] if saved_by else []),
        "## Misses",
        "",
    ]
    for row, got, wrong in misses:
        detail = ", ".join(f"{f}: expected {row['expected'][f]!r}, got {got.get(f)!r}" for f in wrong)
        lines.append(f"- #{row['id']} “{row['text']}”: {detail}")
    report = "\n".join(lines) + "\n"
    sys.stdout.buffer.write(report.encode("utf-8"))
    if args.write:
        (ROOT / "docs" / "eval.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
