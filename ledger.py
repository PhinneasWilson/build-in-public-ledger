#!/usr/bin/env python3
"""build-in-public-ledger: log projects, pitches, replies and dollars earned, then publish a stats page.

Everything lives in one local JSON file (ledger.json). `build` writes a static index.html with the
totals and a timeline you can host on GitHub Pages. Money is stored in whole cents so totals are exact.
Pitch recipients are private by default: the public page shows a pitch's date and channel, and only
shows who it went to when you add --public-label.

    python ledger.py init                       # seed: quakewatch and faqbot pushed 2026-10-19, $0 earned
    python ledger.py project "name" --url https://github.com/... --date 2026-10-19
    python ledger.py pitch --channel email --about "website redesign" [--public-label "a local plumber"] [--date D]
    python ledger.py reply --pitch 3 --note "asked for a quote"
    python ledger.py earn 150.00 --source "website redesign" [--date D]
    python ledger.py stats
    python ledger.py build -o index.html
    python ledger.py --test

Standard library only.
"""
import argparse
import html
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DEFAULT_DB = "ledger.json"
KINDS = ("project", "pitch", "reply", "earning")

SEED = [
    {"kind": "project", "date": "2026-10-19", "title": "quakewatch", "url": "https://github.com/PhinneasWilson/quakewatch",
     "detail": "pushed to GitHub"},
    {"kind": "project", "date": "2026-10-19", "title": "faqbot", "url": "https://github.com/PhinneasWilson/faqbot",
     "detail": "pushed to GitHub"},
]


# ---------------------------------------------------------------- storage
def load(path):
    if not os.path.exists(path):
        return {"entries": []}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("entries", [])
    return data


def save(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def parse_day(text):
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def to_cents(text):
    try:
        value = Decimal(str(text).replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        raise ValueError(f"not a dollar amount: {text!r}")
    if value < 0:
        raise ValueError("amount cannot be negative")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValueError("use at most two decimal places")
    return int(cents)


def money(cents):
    return f"${cents // 100:,}.{cents % 100:02d}"


def add(data, kind, day=None, **fields):
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    entry = {"id": max((e["id"] for e in data["entries"]), default=0) + 1, "kind": kind,
             "date": parse_day(day) if day else date.today().isoformat()}
    entry.update({k: v for k, v in fields.items() if v not in (None, "")})
    data["entries"].append(entry)
    return entry


def seed(data):
    have = {(e["kind"], e.get("title")) for e in data["entries"]}
    added = 0
    for item in SEED:
        if (item["kind"], item["title"]) not in have:
            fields = {k: v for k, v in item.items() if k not in ("kind", "date")}
            add(data, item["kind"], item["date"], **fields)
            added += 1
    return added


# ---------------------------------------------------------------- commands
def add_project(data, name, url="", day=None):
    if not name.strip():
        raise ValueError("a project needs a name")
    return add(data, "project", day, title=name.strip(), url=url.strip(), detail="pushed to GitHub" if "github.com" in url else "")


def add_pitch(data, channel, about, label="", day=None):
    if not channel.strip() or not about.strip():
        raise ValueError("a pitch needs a channel and what it was about")
    return add(data, "pitch", day, channel=channel.strip(), title=about.strip(), public_label=label.strip())


def add_reply(data, pitch_id, note="", day=None):
    pitches = {e["id"] for e in data["entries"] if e["kind"] == "pitch"}
    if pitch_id not in pitches:
        raise KeyError(f"no pitch with id {pitch_id}")
    return add(data, "reply", day, pitch_id=pitch_id, detail=note.strip())


def add_earning(data, amount, source, day=None):
    cents = to_cents(amount)
    if not source.strip():
        raise ValueError("an earning needs a source")
    return add(data, "earning", day, amount_cents=cents, title=source.strip())


def stats(data):
    by = {k: [e for e in data["entries"] if e["kind"] == k] for k in KINDS}
    pitched = {e["id"] for e in by["pitch"]}
    replied = {e["pitch_id"] for e in by["reply"] if e.get("pitch_id") in pitched}
    earned = sum(e["amount_cents"] for e in by["earning"])
    return {
        "projects": len(by["project"]),
        "pitches": len(by["pitch"]),
        "pitches_with_reply": len(replied),
        "reply_rate": (len(replied) / len(by["pitch"])) if by["pitch"] else None,
        "earned_cents": earned,
        "payments": len(by["earning"]),
    }


def format_stats(data):
    s = stats(data)
    rate = "n/a (no pitches yet)" if s["reply_rate"] is None else f"{s['reply_rate'] * 100:.0f}% ({s['pitches_with_reply']} of {s['pitches']})"
    return (f"projects shipped: {s['projects']}\npitches sent:     {s['pitches']}\n"
            f"reply rate:       {rate}\nearned:           {money(s['earned_cents'])} from {s['payments']} payment(s)")


# ---------------------------------------------------------------- page
def describe(entry):
    e = html.escape
    kind = entry["kind"]
    if kind == "project":
        name = e(entry["title"])
        if entry.get("url"):
            name = f'<a href="{e(entry["url"], quote=True)}" rel="noopener">{name}</a>'
        return f"Shipped {name}"
    if kind == "pitch":
        who = f" to {e(entry['public_label'])}" if entry.get("public_label") else ""
        return f"Pitch #{entry['id']} sent by {e(entry['channel'])}{who}: {e(entry['title'])}"
    if kind == "reply":
        note = f" ({e(entry['detail'])})" if entry.get("detail") else ""
        return f"Reply to pitch #{entry['pitch_id']}{note}"
    return f"Earned {money(entry['amount_cents'])} from {e(entry['title'])}"


def build_page(data, title="Build in public"):
    s = stats(data)
    rate = "n/a" if s["reply_rate"] is None else f"{s['reply_rate'] * 100:.0f}%"
    rows = sorted(data["entries"], key=lambda e: (e["date"], e["id"]), reverse=True)
    items = "\n".join(f"<li><time>{html.escape(e['date'])}</time> {describe(e)}</li>" for e in rows) or "<li>Nothing logged yet.</li>"
    cards = [("Projects shipped", s["projects"]), ("Pitches sent", s["pitches"]), ("Reply rate", rate), ("Earned", money(s["earned_cents"]))]
    tiles = "".join(f'<div class="t"><b>{html.escape(str(v))}</b><span>{k}</span></div>' for k, v in cards)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>body{{font-family:system-ui,sans-serif;max-width:42em;margin:1.5em auto;padding:0 1em}}"
        ".g{display:flex;gap:.6em;flex-wrap:wrap}.t{border:1px solid #ddd;border-radius:8px;padding:.6em 1em;flex:1;min-width:7em}"
        ".t b{display:block;font-size:1.5em}.t span{color:#555;font-size:.85em}li{margin:.4em 0}time{color:#666;margin-right:.5em}"
        f"</style></head><body>\n<h1>{html.escape(title)}</h1>\n<div class=\"g\">{tiles}</div>\n<h2>Timeline</h2>\n<ul>\n{items}\n</ul>\n</body></html>\n"
    )


# ---------------------------------------------------------------- cli
def main(argv=None):
    p = argparse.ArgumentParser(description="Log projects, pitches, replies and earnings, then publish a stats page.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--test", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("init")
    a = sub.add_parser("project")
    a.add_argument("name")
    a.add_argument("--url", default="")
    a.add_argument("--date")
    a = sub.add_parser("pitch")
    a.add_argument("--channel", required=True)
    a.add_argument("--about", required=True)
    a.add_argument("--public-label", default="")
    a.add_argument("--date")
    a = sub.add_parser("reply")
    a.add_argument("--pitch", type=int, required=True)
    a.add_argument("--note", default="")
    a.add_argument("--date")
    a = sub.add_parser("earn")
    a.add_argument("amount")
    a.add_argument("--source", required=True)
    a.add_argument("--date")
    sub.add_parser("stats")
    a = sub.add_parser("build")
    a.add_argument("-o", "--output", default="index.html")
    a.add_argument("--title", default="Build in public")
    args = p.parse_args(argv)
    if args.test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LedgerTests))
        return 0 if result.wasSuccessful() else 1
    if not args.cmd:
        p.print_help()
        return 2
    data = load(args.db)
    try:
        if args.cmd == "init":
            print(f"added {seed(data)} seed entries")
        elif args.cmd == "project":
            print(f"logged project #{add_project(data, args.name, args.url, args.date)['id']}")
        elif args.cmd == "pitch":
            print(f"logged pitch #{add_pitch(data, args.channel, args.about, args.public_label, args.date)['id']}")
        elif args.cmd == "reply":
            print(f"logged reply #{add_reply(data, args.pitch, args.note, args.date)['id']}")
        elif args.cmd == "earn":
            print(f"logged earning #{add_earning(data, args.amount, args.source, args.date)['id']}")
        elif args.cmd == "stats":
            print(format_stats(data))
            return 0
        elif args.cmd == "build":
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(build_page(data, args.title))
            print(f"wrote {args.output}")
            return 0
    except (ValueError, KeyError, OSError) as err:
        print(f"error: {err.args[0]}", file=sys.stderr)
        return 1
    save(args.db, data)
    return 0


class LedgerTests(unittest.TestCase):
    def test_seed_matches_spec_and_is_idempotent(self):
        data = {"entries": []}
        self.assertEqual(seed(data), 2)
        self.assertEqual(seed(data), 0)
        self.assertEqual([(e["title"], e["date"]) for e in data["entries"]], [("quakewatch", "2026-10-19"), ("faqbot", "2026-10-19")])
        s = stats(data)
        self.assertEqual((s["projects"], s["pitches"], s["earned_cents"]), (2, 0, 0))
        self.assertIsNone(s["reply_rate"])
        self.assertIn("$0.00", format_stats(data))

    def test_money_is_exact(self):
        self.assertEqual(to_cents("150"), 15000)
        self.assertEqual(to_cents("$1,234.50"), 123450)
        self.assertEqual(to_cents("0.10") + to_cents("0.20"), 30)
        for bad in ("-5", "abc", "1.234"):
            with self.assertRaises(ValueError):
                to_cents(bad)
        self.assertEqual(money(123450), "$1,234.50")

    def test_reply_rate_counts_pitches_not_replies(self):
        data = {"entries": []}
        for _ in range(4):
            add_pitch(data, "email", "redesign", day="2026-10-20")
        add_reply(data, 1)
        add_reply(data, 1, "second reply, same pitch")
        add_reply(data, 2)
        s = stats(data)
        self.assertEqual((s["pitches"], s["pitches_with_reply"]), (4, 2))
        self.assertAlmostEqual(s["reply_rate"], 0.5)
        with self.assertRaises(KeyError):
            add_reply(data, 99)

    def test_earnings_total(self):
        data = {"entries": []}
        add_earning(data, "150", "site A", "2026-10-21")
        add_earning(data, "20.50", "bot", "2026-10-22")
        self.assertEqual(stats(data)["earned_cents"], 17050)

    def test_page_hides_pitch_recipient_by_default_and_escapes(self):
        data = {"entries": []}
        seed(data)
        add_pitch(data, "email", "redesign <script>", day="2026-10-20")
        add_pitch(data, "email", "redesign", label="a local plumber", day="2026-10-20")
        page = build_page(data)
        self.assertIn("Pitch #3 sent by email: redesign &lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn("to a local plumber", page)
        self.assertIn("<b>$0.00</b>", page)
        self.assertLess(page.index("Pitch #4"), page.index("Shipped"))

    def test_bad_date_rejected(self):
        with self.assertRaises(ValueError):
            add_project({"entries": []}, "x", day="19/10/2026")

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "l.json")
            base = ["--db", db]
            self.assertEqual(main(base + ["init"]), 0)
            self.assertEqual(main(base + ["pitch", "--channel", "email", "--about", "redesign", "--date", "2026-10-20"]), 0)
            self.assertEqual(main(base + ["reply", "--pitch", "3"]), 0)
            self.assertEqual(main(base + ["reply", "--pitch", "42"]), 1)
            self.assertEqual(main(base + ["earn", "150", "--source", "site"]), 0)
            self.assertEqual(stats(load(db))["earned_cents"], 15000)
            out = os.path.join(tmp, "i.html")
            self.assertEqual(main(base + ["build", "-o", out]), 0)
            self.assertIn("$150.00", open(out, encoding="utf-8").read())


if __name__ == "__main__":
    sys.exit(main())
