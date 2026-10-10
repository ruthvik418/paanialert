# Extraction accuracy

Scored with `python scripts/eval_extraction.py [--method fallback|agent]` on the 50 labelled messages in `data/test_messages.jsonl` (15 Hindi in Roman script, 10 Devanagari, 10 English, 10 Hinglish with typos, 5 negations). A message counts as right only if all five fields match: smell, colour, taste, since_days, sick_count.

## Keyword fallback (`src/agent/fallback.py`)

| Run | All five fields right | Notes |
|---|---|---|
| Oct 8, first version | 33/50 (66%) | Per field: smell 92%, colour 94%, taste 98%, since_days 92%, sick_count 88% |
| Oct 8, after fixes | 50/50 (100%) | **Tuned on this same set, so this overstates real accuracy** |

The fixes were general (Hindi and English number words, "aaj subah se", common typos like "bdboo" and "gnda", "no smell", "kharab" not meaning "khara"), but they were made while looking at these messages. For an honest number, someone who hasn't seen the rules should write 20–30 fresh messages into `data/test_messages_holdout.jsonl` and score them once.

## Bedrock agent (Mantle, `ap-south-1`)

`--method agent` scores the live bot's path: `runner.reply` with `SYSTEM_PROMPT`, the `save_report` tool and the model fallback chain (the save is captured, nothing is written). A message the models didn't save counts as wrong here, although in production it is saved by keywords.

| Run | Model order | All five fields right | Saved by |
|---|---|---|---|
| Oct 10 | `deepseek.v3.1`, `qwen.qwen3-235b-a22b-2507`, `qwen.qwen3-vl-235b-a22b-instruct` (deployed) | **21/50 (42%)** | DeepSeek 2, Qwen3 235B 26, Qwen3 VL 7, no model 13, not saved 2 |
| Oct 10 | Qwen3 235B, Qwen3 VL, DeepSeek V3.1 | 22/50 (44%) | Qwen3 235B 27, Qwen3 VL 6, no model 15, not saved 2 |

Per field (deployed order): smell 68%, colour 62%, taste 70%, since_days 86%, sick_count 72%.

What drags it down:

- **Asking for a location before saving.** All three models often reply "Could you share your location? Attach (📎) → Location so I can report this" instead of calling `save_report` (DeepSeek V3.1 almost always). The runner treats that as a failure and tries the next model; 13–15 of 50 complaints end up with keywords. The system prompt says both "save as soon as you know what is wrong" and "ask for a location pin"; making it say "save first, then ask for the pin" should fix most of these.
- **sick_count 0 when nobody mentioned sickness** (expected empty), and **"matmaila" read as cloudy** (expected brown).

The old `--method structured` path (`agent/extract.py`, one structured-output call with `EXTRACT_PROMPT`) scored 13/50 (26%): that prompt lists no allowed values or Hindi examples, so the models answer "peela" or "bad" and the schema turns them into `unknown`. The bot doesn't use that path.
