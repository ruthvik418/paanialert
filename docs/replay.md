# Indore replay

**SIMULATION.** Every report here is synthetic. Nobody sent them. They follow the public timeline of the Dec 2025 Bhagirathpura, Indore outbreak (`docs/sources.md`) to ask one question: if some residents had been reporting to PaaniAlert, when would our real cluster rule have raised a Watch and an Alert?

```bash
python scripts/replay.py --seeds 100     # the table below
python scripts/replay.py --false-alarms  # the three must-not-alert cases
python scripts/replay.py --write         # regenerate data/replay_*.jsonl (seeded, so identical)
```

The script steps through 15–29 Dec in 1-hour steps and calls `cluster.rule.evaluate()` itself at each step (no copy of the rule), with the same 48-hour window, thresholds and neighbourhood as production.

## Assumptions

| What | Assumed | Why |
|---|---|---|
| Place | Homes within 400 m of 22.733, 75.858 (Bhagirathpura) | One colony on one supply line |
| Households on the contaminated supply | 1,000 | Not published. ~1,400 people fell ill (figure still to be confirmed, `docs/sources.md`) |
| Adoption | 2%, 5%, 10% of those households report (20, 50, 100 reports) | Unknown, so three levels instead of one number |
| Reports | One per reporting household, when it first notices the problem, 07:00–22:00 IST | Repeat reports from the same phone don't add phones to the rule anyway |
| When households first report | 10% between ~15 and 24 Dec (foul, discoloured water); 35% on 25–26 Dec (bitter taste, strong odour); 55% on 27–29 Dec | Shaped on the timeline: a few early complaints, many from 25 Dec, illness from 27 Dec |
| What they report | Before 25 Dec: sewage or odd smell, yellow/brown/murky water. From 25 Dec: sewage smell and bad taste. From 27 Dec: 60% also report someone sick | Same timeline |
| "First illness" | 27 Dec 00:00 IST | The source gives the day, not the hour |
| Randomness | Seed 1 for the data file and the first columns; seeds 1–100 for the spread | Reproducible; shows how much one run's luck matters |

Higher adoption levels contain every report of the lower ones (each record has a `rank`).

## Results

| Adoption | Reporting households | First Watch | First Alert | Watch vs first illness | Alert vs first illness | Watch, 100 seeds: median days before (range) | Alert, 100 seeds: median days before (range) |
|---|---|---|---|---|---|---|---|
| 2% | 20 (5 with someone sick) | 25 Dec 17:00 | 26 Dec 15:00 | 1.3 days before | 0.4 days before | 1.5 (0.5 to 11.2) | 0.5 (−1.4 to 1.4) |
| 5% | 50 (16 with someone sick) | 25 Dec 12:00 | 26 Dec 08:00 | 1.5 days before | 0.7 days before | 3.9 (1.4 to 11.2) | 1.4 (0.6 to 10.2) |
| 10% | 100 (29 with someone sick) | 16 Dec 11:00 | 25 Dec 12:00 | 10.5 days before | 1.5 days before | 9.4 (1.7 to 11.4) | 1.6 (1.4 to 11.1) |

Times are IST. A negative number means after the first illness.

**Where the lead comes from.** The Alert almost always fires on 25–26 Dec, from 5 different phones complaining about taste and smell inside 48 hours, before any illness report. A Watch comes earlier only when enough of the few mid-December reporters fall within the same 48 hours: at 10% adoption that happened in most runs (median 9.4 days ahead), at 2% rarely.

## False alarms

`data/replay_false_alarm.jsonl`, checked by `tests/test_replay.py`:

| Case | Highest level | Why it stops there |
|---|---|---|
| (a) One person sends 10 complaints in a day | Watch | Their severity adds up past 10, but it's 1 phone; Alert needs 5 phones or 2 sick households |
| (b) Murky water that clears quickly, 4 homes, after supply resumes | Watch | 4 phones (Watch needs 3, Alert 5); clears-quickly halves the severity |
| (c) 6 homes, 2 with someone sick, inside an active maintenance notice | Watch | Without the notice this is an Alert (the test checks that too); the notice caps it at Watch |

None reaches Alert. All three still show as Watch, which is intended: someone should look, but nobody is told to boil water.

## What this does and doesn't show

It shows that the cluster rule, fed complaints shaped like the Indore timeline, would have raised an Alert before the first illnesses in all 100 seeded runs at 5% and 10% adoption, and in 90 of 100 at 2%. But the usual lead is about a day and a half, not weeks, because the rule waits for 5 phones in 48 hours and the timeline's complaints only surged on 25 Dec. The 10-day-early Watch depends on early reporters that we assumed (10% of reporting households before 25 Dec), not on anything measured. It does not show that residents would have used PaaniAlert, that 1,000 households were affected, that officials would have acted on an Alert, or that acting a day or two earlier would have saved lives; the judicial commission's finding that the contamination "could have been prevented" is about the pipeline and the response, not about this tool. Say "simulation" whenever these numbers are shown.

## For the video: `--load`

```bash
python scripts/replay.py --load --adoption 0.05   # put the 5% replay into the live Reports table
python scripts/replay.py --clean                  # remove it (fake_reports.py --clean also removes it)
```

`--load` squeezes 15–29 Dec into the last 48 hours of real time, so the cluster map shows the outbreak build up. The reports have ids starting `fake-replay-`, the name "SIMULATION · Indore replay" on the dashboard, and "(SIMULATION)" at the end of the message text.

The next cluster check (within 15 minutes) will turn them into an Alert, and an Alert really sends: WhatsApp advisories to subscribers in those cells, and email to the ward engineer's SNS topic (then the health officer after `EscalateAfterMin`). `--load` refuses if a real subscriber has a pin in the area, unless you pass `--allow-alerts`; the officials' emails go out either way, so warn whoever is subscribed to those topics.
