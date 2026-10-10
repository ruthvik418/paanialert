"""Replay the Dec 2025 Indore (Bhagirathpura) outbreak through the real cluster rule. Owner: C.

SIMULATION. The reports are synthetic, built from the timeline in docs/sources.md;
nobody sent them. See docs/replay.md for the assumptions and what this does and
doesn't show.

    python scripts/replay.py                  # 2%, 5% and 10% adoption, from data/replay_indore.jsonl
    python scripts/replay.py --seeds 100      # also the spread over 100 differently seeded runs
    python scripts/replay.py --false-alarms   # the three cases in data/replay_false_alarm.jsonl
    python scripts/replay.py --write          # regenerate both data files (seeded, so identical)
    python scripts/replay.py --load --adoption 0.05   # put the replay into the live tables (last 48 h)
    python scripts/replay.py --clean          # remove it again (fake_reports.py --clean also does)

The rule is called, never copied: cluster.rule.evaluate() at every 1-hour step.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cluster.rule import evaluate  # noqa: E402
from common.geo import geohash6, neighbourhood  # noqa: E402
from common.models import Report, from_item  # noqa: E402

INDORE_FILE = ROOT / "data" / "replay_indore.jsonl"
FALSE_ALARM_FILE = ROOT / "data" / "replay_false_alarm.jsonl"

IST = timezone(timedelta(hours=5, minutes=30))
CENTRE = (22.733, 75.858)                      # Bhagirathpura, Indore (approximate)
RADIUS_M = 400                                 # homes spread within this distance of the centre
START = datetime(2025, 12, 15, tzinfo=IST)     # ~15 Dec: foul, discoloured water noticed (approximate)
TASTE_ODOUR = datetime(2025, 12, 25, tzinfo=IST)   # 25 Dec: bitter taste and strong odour widely reported
FIRST_ILLNESS = datetime(2025, 12, 27, tzinfo=IST)  # 27 Dec: residents fall ill (vomiting, diarrhoea)
END = datetime(2025, 12, 30, tzinfo=IST)       # replay runs to the end of 29 Dec (deaths confirmed that day)
STEP = timedelta(hours=1)
SEED = 1
ADOPTION_LEVELS = (0.02, 0.05, 0.10)

# ASSUMPTIONS (also written into the data file's header and docs/replay.md).
AFFECTED_HOUSEHOLDS = 1000   # households on the contaminated supply; not published. ~1,400 people fell ill.
# When a reporting household first reports: share in each phase of the timeline.
PHASES = [  # (name, start, end, share of reporting households)
    ("foul water noticed", START, TASTE_ODOUR, 0.10),
    ("bitter taste, strong odour", TASTE_ODOUR, FIRST_ILLNESS, 0.35),
    ("illness", FIRST_ILLNESS, END, 0.55),
]
SICK_SHARE_FROM_27 = 0.6     # of households reporting from 27 Dec, the share reporting someone sick
DAY_HOURS = (7, 22)          # people send messages between 07:00 and 22:00 IST

HEADER = {
    "type": "header",
    "label": "SIMULATION",
    "note": ("Synthetic PaaniAlert reports for the Dec 2025 Bhagirathpura, Indore outbreak. Nobody sent these. "
             "Built by scripts/replay.py from the timeline in docs/sources.md; see docs/replay.md."),
    "assumptions": {
        "centre": CENTRE, "radius_m": RADIUS_M, "affected_households": AFFECTED_HOUSEHOLDS,
        "phases": [{"phase": n, "from": s.date().isoformat(), "to_before": e.date().isoformat(), "share": w}
                   for n, s, e, w in PHASES],
        "sick_share_from_27_dec": SICK_SHARE_FROM_27, "message_hours_ist": DAY_HOURS,
        "one_report_per_household": True,
        "adoption": ("records carry 'rank'; adoption p uses the households with rank <= p * affected_households, "
                     "so a higher adoption level contains every report of a lower one"),
    },
    "seed": SEED,
}


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _near(rng: random.Random, lat: float, lon: float, metres: float) -> tuple[float, float]:
    angle, dist = rng.uniform(0, 2 * math.pi), metres * math.sqrt(rng.random())
    return (round(lat + dist * math.cos(angle) / 111_320, 6),
            round(lon + dist * math.sin(angle) / (111_320 * math.cos(math.radians(lat))), 6))


def _when(rng: random.Random, start: datetime, end: datetime) -> datetime:
    day = start + timedelta(days=rng.randrange((end - start).days))
    return day + timedelta(minutes=rng.randrange(DAY_HOURS[0] * 60, DAY_HOURS[1] * 60))


def build_indore(seed: int = SEED, max_adoption: float = max(ADOPTION_LEVELS)) -> list[dict]:
    """One report per reporting household, for the highest adoption level, in rank order."""
    rng = random.Random(seed)
    records = []
    for rank in range(1, round(max_adoption * AFFECTED_HOUSEHOLDS) + 1):
        phase, start, end, _ = rng.choices(PHASES, weights=[p[3] for p in PHASES])[0]
        lat, lon = _near(rng, *CENTRE, RADIUS_M)
        sick = phase == "illness" and rng.random() < SICK_SHARE_FROM_27
        rec = {
            "simulation": True, "rank": rank, "phase": phase,
            "report_id": f"replay-indore-{rank:03d}", "phone_hash": f"replay-phone-{rank:03d}",
            "created_at": _iso(_when(rng, start, end)),
            "lat": lat, "lon": lon, "geohash6": geohash6(lat, lon),
            "smell": "sewage" if phase != "foul water noticed" else rng.choice(["sewage", "other"]),
            "colour": rng.choice(["yellow", "brown", "cloudy"]),
            "taste": "bad" if phase != "foul water noticed" else "unknown",
            "since_days": None, "sick_count": rng.randint(1, 3) if sick else None,
            "symptoms": rng.sample(["diarrhoea", "vomiting", "fever"], 2) if sick else [],
            "source": "pipe", "lang": rng.choice(["hinglish", "hinglish", "hi"]),
        }
        records.append(rec)
    return records


def build_false_alarms() -> list[dict]:
    """Three cases that must stay below Alert, each in its own part of Indore so they can't interact."""
    t0 = datetime(2025, 11, 3, 9, tzinfo=IST)
    base = {"simulation": True, "source": "pipe", "lang": "hinglish", "taste": "unknown", "since_days": None,
            "symptoms": [], "clears_quickly": None}
    rows: list[dict] = []
    rng = random.Random(SEED)

    # (a) One person sends 10 complaints in a day.
    lat, lon = 22.6900, 75.8100
    for i in range(10):
        rows.append({**base, "case": "a", "report_id": f"replay-fa-a-{i:02d}", "phone_hash": "replay-fa-a-phone",
                     "created_at": _iso(t0 + timedelta(hours=i * 1.5)), "lat": lat, "lon": lon,
                     "geohash6": geohash6(lat, lon), "smell": "sewage", "colour": "yellow", "sick_count": None})

    # (b) Murky water that clears after running, in 4 homes, the morning supply resumes after a repair.
    for i in range(4):
        la, lo = _near(rng, 22.7600, 75.9000, 250)
        rows.append({**base, "case": "b", "report_id": f"replay-fa-b-{i:02d}", "phone_hash": f"replay-fa-b-phone-{i}",
                     "created_at": _iso(t0 + timedelta(hours=i)), "lat": la, "lon": lo, "geohash6": geohash6(la, lo),
                     "smell": "none", "colour": "cloudy", "sick_count": 0, "clears_quickly": True})

    # (c) 6 homes complain inside an area with an active maintenance notice.
    lat, lon = 22.7000, 75.9000
    rows.append({"type": "notice", "case": "c", "geohash6": geohash6(lat, lon),
                 "text": "Pipeline repair, supply may be dirty for 2 days (SIMULATION)"})
    for i in range(6):
        la, lo = _near(rng, lat, lon, 250)
        rows.append({**base, "case": "c", "report_id": f"replay-fa-c-{i:02d}", "phone_hash": f"replay-fa-c-phone-{i}",
                     "created_at": _iso(t0 + timedelta(hours=2 * i)), "lat": la, "lon": lo,
                     "geohash6": geohash6(la, lo), "smell": "sewage", "colour": "brown",
                     "sick_count": 1 if i < 2 else None, "symptoms": ["diarrhoea"] if i < 2 else []})
    return rows


FALSE_ALARM_HEADER = {
    "type": "header", "label": "SIMULATION",
    "note": ("Synthetic cases that must NOT reach Alert: (a) one person sends 10 complaints, (b) murky water that "
             "clears quickly in 4 homes after supply resumes, (c) 6 homes inside an active maintenance-notice area. "
             "Built by scripts/replay.py; checked by tests/test_replay.py."),
}


def write_files() -> None:
    for path, header, rows in ((INDORE_FILE, HEADER, build_indore()),
                               (FALSE_ALARM_FILE, FALSE_ALARM_HEADER, build_false_alarms())):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for row in [header, *rows]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def read(path: Path) -> tuple[dict, list[dict]]:
    """The header and the rows of a replay file."""
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    if rows[0].get("type") != "header" or rows[0].get("label") != "SIMULATION":
        raise ValueError(f"{path.name} must start with the SIMULATION header line")
    return rows[0], rows[1:]


def to_report(rec: dict) -> Report:
    return from_item(Report, rec)


def adopt(records: list[dict], adoption: float) -> list[dict]:
    return [r for r in records if r["rank"] <= round(adoption * AFFECTED_HOUSEHOLDS)]


def step_through(reports: list[Report], start: datetime, end: datetime,
                 notice_cells: frozenset = frozenset()) -> dict[str, datetime | None]:
    """First time the real rule puts any cluster at Watch and at Alert, checking every hour."""
    first: dict[str, datetime | None] = {"watch": None, "alert": None}
    t = start
    while t <= end and first["alert"] is None:
        levels = {c.level for c in evaluate(reports, t.astimezone(timezone.utc), notice_cells)}
        if levels and first["watch"] is None:
            first["watch"] = t          # an Alert is also at least a Watch
        if "alert" in levels:
            first["alert"] = t
        t += STEP
    return first


def lead_days(t: datetime | None) -> float | None:
    """Days before the first illness (27 Dec); negative means after."""
    return None if t is None else round((FIRST_ILLNESS - t) / timedelta(days=1), 1)


def replay(records: list[dict], adoption: float) -> dict:
    chosen = adopt(records, adoption)
    first = step_through([to_report(r) for r in chosen], START, END)
    return {"adoption": adoption, "reports": len(chosen),
            "sick_reports": sum(1 for r in chosen if r.get("sick_count")),
            "first_watch": first["watch"], "first_alert": first["alert"],
            "watch_lead_days": lead_days(first["watch"]), "alert_lead_days": lead_days(first["alert"])}


def false_alarm_levels() -> dict[str, str]:
    """The highest level each false-alarm case reaches over its whole run."""
    _, rows = read(FALSE_ALARM_FILE)
    out = {}
    for case in sorted({r["case"] for r in rows}):
        reports = [to_report(r) for r in rows if r["case"] == case and r.get("type") != "notice"]
        notices = frozenset(r["geohash6"] for r in rows if r["case"] == case and r.get("type") == "notice")
        times = sorted(_parse(r.created_at) for r in reports)
        first = step_through(reports, times[0], times[-1] + timedelta(hours=48), notices)
        out[case] = "alert" if first["alert"] else "watch" if first["watch"] else "none"
    return out


def _fmt(t: datetime | None) -> str:
    return t.astimezone(IST).strftime("%d %b %H:%M") if t else "never"


def _lead(d: float | None) -> str:
    if d is None:
        return "–"
    return f"{d} days before" if d >= 0 else f"{-d} days after"


def _spread(leads: list[float | None]) -> str:
    known = [d for d in leads if d is not None]
    never = len(leads) - len(known)
    text = f"{round(statistics.median(known), 1)} ({min(known)} to {max(known)})" if known else "never"
    return text + (f", {never} never" if never else "")


def print_table(results: list[dict], spread: dict[float, dict[str, list[float | None]]] | None) -> None:
    print("SIMULATION: Indore, Bhagirathpura, Dec 2025 (first illness 27 Dec)\n")
    extra = [f"Watch, {len(spread[ADOPTION_LEVELS[0]]['watch'])} seeds", "Alert, same seeds"] if spread else []
    print("| Adoption | Reporting households | First Watch | First Alert | Watch vs first illness | "
          "Alert vs first illness |" + "".join(f" {e}: median days before (range) |" for e in extra))
    print("|---|---|---|---|---|---|" + "---|" * len(extra))
    for r in results:
        row = (f"| {r['adoption']:.0%} | {r['reports']} ({r['sick_reports']} with someone sick) | {_fmt(r['first_watch'])} | "
               f"{_fmt(r['first_alert'])} | {_lead(r['watch_lead_days'])} | {_lead(r['alert_lead_days'])} |")
        if spread:
            row += f" {_spread(spread[r['adoption']]['watch'])} | {_spread(spread[r['adoption']]['alert'])} |"
        print(row)


def seed_spread(n: int) -> dict[float, dict[str, list[float | None]]]:
    spread = {a: {"watch": [], "alert": []} for a in ADOPTION_LEVELS}
    for seed in range(1, n + 1):
        records = build_indore(seed)
        for a in ADOPTION_LEVELS:
            r = replay(records, a)
            spread[a]["watch"].append(r["watch_lead_days"])
            spread[a]["alert"].append(r["alert_lead_days"])
    return spread


# Loading into the live tables, for the video

def _session():
    import os

    import boto3
    return boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "paani"),
                         region_name=os.environ.get("AWS_REGION", "ap-south-1"))


def load(adoption: float, allow_alerts: bool) -> None:
    """Write the replay into the Reports table, Dec 15-30 squeezed into the last 48 hours of real time."""
    from decimal import Decimal

    from boto3.dynamodb.conditions import Attr

    from fake_reports import resource_id

    _, records = read(INDORE_FILE)
    chosen = adopt(records, adoption)
    session = _session()
    ddb = session.resource("dynamodb")

    # The cluster check (every 15 min) will raise an Alert from these: it WhatsApps subscribers in the
    # area and emails the officials' SNS topics. Refuse if a real subscriber is in the area.
    cells = sorted({c for r in chosen for c in neighbourhood(r["geohash6"])})
    subscribers = ddb.Table(resource_id(session, "SubscribersTable"))
    real = [s for s in subscribers.scan(FilterExpression=Attr("geohash6").is_in(cells))["Items"]
            if not str(s.get("phone_hash", "")).startswith("fake-")]
    if real and not allow_alerts:
        sys.exit(f"{len(real)} real subscriber(s) have a pin in this area and would get a WhatsApp alert. "
                 "Re-run with --allow-alerts if that's intended.")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    squeeze = timedelta(hours=48) / (END - START)
    table = ddb.Table(resource_id(session, "ReportsTable"))
    with table.batch_writer() as batch:
        for r in chosen:
            at = now - timedelta(hours=48) + (_parse(r["created_at"]) - START) * squeeze
            item = {k: v for k, v in r.items() if k not in ("rank", "phase") and v not in (None, [])}
            item.update(
                report_id=f"fake-{r['report_id']}", phone_hash=f"fake-{r['phone_hash']}",
                created_at=_iso(at), lat=Decimal(str(r["lat"])), lon=Decimal(str(r["lon"])),
                profile_name="SIMULATION · Indore replay", landmark="TEST REPORT", text=_message(r),
            )
            batch.put_item(Item=item)
    print(f"Loaded {len(chosen)} SIMULATION reports ({adoption:.0%} adoption), 15-29 Dec squeezed into the last "
          "48 hours. The cluster check picks them up within 15 minutes; remove with --clean.")


def _message(r: dict) -> str:
    colour = {"yellow": "peela", "brown": "bhura", "cloudy": "gandla"}[r["colour"]]
    text = f"Nal ka paani {colour} aa raha hai, " + ("gutter jaisi badboo hai" if r["smell"] == "sewage" else "ajeeb smell hai")
    if r["taste"] == "bad":
        text += ", swad kadwa hai"
    if r.get("sick_count"):
        text += f". Ghar mein {r['sick_count']} log bimar hain, ulti dast."
    return text + " (SIMULATION)"


def clean() -> None:
    from fake_reports import clean as clean_fake
    clean_fake(_session(), prefix="fake-replay-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, default=0, help="also show the spread over this many seeds")
    parser.add_argument("--false-alarms", action="store_true")
    parser.add_argument("--write", action="store_true", help="regenerate the data files")
    parser.add_argument("--load", action="store_true", help="write the replay into the live tables")
    parser.add_argument("--adoption", type=float, default=0.05, help="for --load (default 0.05)")
    parser.add_argument("--allow-alerts", action="store_true", help="--load even if real subscribers are nearby")
    parser.add_argument("--clean", action="store_true", help="remove loaded replay reports")
    args = parser.parse_args()

    if args.write:
        write_files()
    if args.clean:
        clean()
    if args.load:
        load(args.adoption, args.allow_alerts)
    if args.clean or args.load:
        return
    if args.false_alarms:
        for case, level in false_alarm_levels().items():
            print(f"case {case}: highest level {level}")
        return
    _, records = read(INDORE_FILE)
    print_table([replay(records, a) for a in ADOPTION_LEVELS], seed_spread(args.seeds) if args.seeds else None)


if __name__ == "__main__":
    main()
