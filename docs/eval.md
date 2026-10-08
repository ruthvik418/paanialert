# Extraction accuracy

Scored with `python scripts/eval_extraction.py [--method fallback|agent]` on the 50 labelled messages in `data/test_messages.jsonl` (15 Hindi in Roman script, 10 Devanagari, 10 English, 10 Hinglish with typos, 5 negations). A message counts as right only if all five fields match: smell, colour, taste, since_days, sick_count.

## Keyword fallback (`src/agent/fallback.py`)

| Run | All five fields right | Notes |
|---|---|---|
| Oct 8, first version | 33/50 (66%) | Per field: smell 92%, colour 94%, taste 98%, since_days 92%, sick_count 88% |
| Oct 8, after fixes | 50/50 (100%) | **Tuned on this same set, so this overstates real accuracy** |

The fixes were general (Hindi and English number words, "aaj subah se", common typos like "bdboo" and "gnda", "no smell", "kharab" not meaning "khara"), but they were made while looking at these messages. For an honest number, someone who hasn't seen the rules should write 20–30 fresh messages into `data/test_messages_holdout.jsonl` and score them once.

## Bedrock agent

Not run yet: Bedrock is blocked on the team account until the overdue invoice clears. Run `python scripts/eval_extraction.py --method agent --write` once it works, and put the agent's number in the video, not the fallback's.
