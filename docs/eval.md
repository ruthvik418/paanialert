# Extraction accuracy

Scored with `python scripts/eval_extraction.py [--method fallback|agent]` on the 50 labelled messages in `data/test_messages.jsonl` (15 Hindi in Roman script, 10 Devanagari, 10 English, 10 Hinglish with typos, 5 negations). A message counts as right only if all five fields match: smell, colour, taste, since_days, sick_count.

## Keyword fallback (`src/agent/fallback.py`)

| Run | All five fields right | Notes |
|---|---|---|
| Oct 8, first version | 33/50 (66%) | Per field: smell 92%, colour 94%, taste 98%, since_days 92%, sick_count 88% |
| Oct 8, after fixes | 50/50 (100%) | **Tuned on this same set, so this overstates real accuracy** |

The fixes were general (Hindi and English number words, "aaj subah se", common typos like "bdboo" and "gnda", "no smell", "kharab" not meaning "khara"), but they were made while looking at these messages. For an honest number, someone who hasn't seen the rules should write 20–30 fresh messages into `data/test_messages_holdout.jsonl` and score them once.

## Bedrock agent (Mantle, `ap-south-1`)

`--method agent` scores the live bot's path, `runner.reply` with the model fallback chain (the save is captured, nothing is written). A message no model saved counts as wrong here, although in production keywords would save it.

| Run | How the bot reads a message | All five fields right | Median per message |
|---|---|---|---|
| Oct 10 | Conversation agent calls a `save_report` tool when it decides to (DeepSeek V3.1, Qwen3 235B, Qwen3 VL) | 19/50 to 21/50 (38–42%) | 3.0 s |
| Oct 10 | **Forced extraction** into `ReportFields`, code saves and replies (Qwen3 235B, Qwen3 VL) | **45/50 to 46/50 (90–92%)** | **1.2 s** (p90 1.6 s) |

Per field, forced extraction (last run): smell 98%, colour 92%, taste 96%, since_days 100%, sick_count 100%. Qwen3 235B read all 50 messages; Qwen3 VL and keywords were never needed.

**Why the jump.** Before, most of the loss was complaints that were never saved (22 of 50): the models asked for a location pin instead of calling the tool. When they did save, values were nearly always right (11 wrong fields in 28 reports, mostly `sick_count` 0 when sickness wasn't mentioned). Forcing the structured output removes the "didn't save" failure, and the field descriptions in `ReportFields` carry the conventions (`since_days` 0 for "aaj subah se", `sick_count` null unless sickness is mentioned).

**Remaining misses:** "khara" read as a bad taste instead of salty, "pila" (yellow, misspelt) read as unknown, "matmaila" read as cloudy, worms ("keede") read as cloudy, and #35 "Something is wrong with the water", which has nothing to save, so the bot asks what's wrong instead (scored as a miss).

**Caveat:** the colour and smell word lists in `ReportFields` overlap with words in these 50 messages (they are the same everyday words the keyword fallback uses), so like the fallback this overstates real accuracy. Score a fresh holdout set (`data/test_messages_holdout.jsonl`, written by someone who hasn't seen the rules) before quoting a number.
