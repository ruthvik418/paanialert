"""Check which Bedrock models work through the friend's role, and pick the best. Owner: B.

    py -3.12 scripts/pick_model.py --role-arn <ARN> --region us-west-2          # quick check
    py -3.12 scripts/pick_model.py --role-arn <ARN> --region us-west-2 --eval   # + 50-message test

For each candidate: does it answer, does it call a tool correctly on a Hinglish
complaint (the agent depends on tool calls), and how fast. --eval also scores
field extraction on data/test_messages.jsonl. Prints the samconfig.toml line
for the best two. See docs/bedrock-access.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CANDIDATES = [
    ("Llama 4 Maverick 17B", ["us.meta.llama4-maverick-17b-instruct-v1:0", "meta.llama4-maverick-17b-instruct-v1:0"]),
    ("DeepSeek V3.1", ["deepseek.v3-v1:0", "us.deepseek.v3-v1:0"]),
    ("Llama 3.3 70B", ["us.meta.llama3-3-70b-instruct-v1:0", "meta.llama3-3-70b-instruct-v1:0"]),
    ("GLM 4.7", ["zai.glm-4.7"]),
    ("MiniMax M2.1", ["minimax.minimax-m2.1"]),
    ("Llama 4 Scout 17B", ["us.meta.llama4-scout-17b-instruct-v1:0", "meta.llama4-scout-17b-instruct-v1:0"]),
    ("Gemma 3 27B", ["google.gemma-3-27b-it"]),
]

TOOL = {"tools": [{"toolSpec": {
    "name": "save_report",
    "description": "Save a resident's complaint about their drinking water.",
    "inputSchema": {"json": {
        "type": "object",
        "properties": {
            "smell": {"type": "string", "enum": ["none", "sewage", "chemical", "other", "unknown"]},
            "colour": {"type": "string", "enum": ["clear", "yellow", "brown", "black", "cloudy", "unknown"]},
            "since_days": {"type": "integer"},
        },
        "required": ["smell", "colour"],
    }},
}}]}
TOOL_PROMPT = "Nal ka paani peela aa raha hai, badboo hai, 2 din se. Save this complaint."


def role_session(role_arn: str, region: str) -> boto3.Session:
    base = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "paani"))
    creds = base.client("sts").assume_role(RoleArn=role_arn, RoleSessionName="paanialert-pick-model")["Credentials"]
    return boto3.Session(aws_access_key_id=creds["AccessKeyId"], aws_secret_access_key=creds["SecretAccessKey"],
                         aws_session_token=creds["SessionToken"], region_name=region)


def probe(client, model_id: str) -> dict:
    out = {"model_id": model_id, "answers": False, "tool_ok": False, "latency_ms": None, "error": ""}
    try:
        start = time.time()
        client.converse(modelId=model_id, messages=[{"role": "user", "content": [{"text": "Reply with exactly: OK"}]}],
                        inferenceConfig={"maxTokens": 10})
        out["answers"] = True
        out["latency_ms"] = int((time.time() - start) * 1000)
        resp = client.converse(modelId=model_id, toolConfig=TOOL, inferenceConfig={"maxTokens": 300, "temperature": 0},
                               messages=[{"role": "user", "content": [{"text": TOOL_PROMPT}]}])
        calls = [b["toolUse"]["input"] for b in resp["output"]["message"]["content"] if "toolUse" in b]
        out["tool_ok"] = bool(calls) and calls[0].get("smell") == "sewage" and calls[0].get("colour") == "yellow"
        if calls and not out["tool_ok"]:
            out["error"] = f"tool input {json.dumps(calls[0])}"
        elif not calls:
            out["error"] = "answered without calling the tool"
    except Exception as exc:  # unavailable model, wrong region, no access
        out["error"] = str(exc).split(":")[-1].strip()[:90]
    return out


def evaluate(model_id: str) -> float | None:
    from agent.extract import extract
    rows = [json.loads(l) for l in open(ROOT / "data" / "test_messages.jsonl", encoding="utf-8") if l.strip()]
    fields = ("smell", "colour", "taste", "since_days", "sick_count")
    right = 0
    for row in rows:
        try:
            got = extract(row["text"], model_id=model_id).model_dump()
            right += all(got.get(f) == row["expected"][f] for f in fields)
        except Exception:
            pass
    return right / len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--eval", action="store_true", help="also score the 50 test messages (a few cents)")
    args = parser.parse_args()

    client = role_session(args.role_arn, args.region).client("bedrock-runtime")
    results = []
    for name, ids in CANDIDATES:
        for model_id in ids:
            r = probe(client, model_id)
            if r["answers"]:
                break
        r["name"] = name
        results.append(r)
        status = "tools OK" if r["tool_ok"] else ("answers" if r["answers"] else "unavailable")
        print(f"{name:22} {r['model_id']:46} {status:12} {r['latency_ms'] or '':>6} ms  {r['error']}")

    usable = [r for r in results if r["tool_ok"]]
    if args.eval and usable:
        os.environ.update(BEDROCK_ROLE_ARN=args.role_arn, BEDROCK_REGION=args.region,
                          AWS_PROFILE=os.environ.get("AWS_PROFILE", "paani"))
        print("\nScoring on 50 test messages (all five fields right):")
        for r in usable:
            r["score"] = evaluate(r["model_id"])
            print(f"  {r['name']:22} {r['score']:.0%}")

    usable.sort(key=lambda r: (-(r.get("score") or 0), r["latency_ms"] or 1e9))
    if not usable:
        sys.exit("\nNo model passed the tool test. Check the role ARN and region (docs/bedrock-access.md).")
    best = ",".join(r["model_id"] for r in usable[:2])
    print(f"\nBest: {usable[0]['name']}. Add this under [default.deploy.parameters] in samconfig.toml, then deploy:")
    print(f'parameter_overrides = "BedrockRoleArn=\\"{args.role_arn}\\" BedrockRegion=\\"{args.region}\\" ModelIds=\\"{best}\\""')


if __name__ == "__main__":
    main()
