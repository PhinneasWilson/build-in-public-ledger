# build-in-public-ledger

One place to log every project shipped, pitch sent, reply received and dollar earned, plus a command that turns the log into a static stats page you can host on GitHub Pages.

One file, Python 3 standard library only. Data lives in a local `ledger.json`. Money is stored in whole cents so totals are exact.

## Use

```
python ledger.py init          # seeds quakewatch and faqbot (both pushed 2026-10-19), $0 earned
python ledger.py project "name" --url https://github.com/... --date 2026-10-19
python ledger.py pitch --channel email --about "website redesign" --public-label "a local plumber"
python ledger.py reply --pitch 3 --note "asked for a quote"
python ledger.py earn 150.00 --source "website redesign"
python ledger.py stats
python ledger.py build -o index.html
python ledger.py --test
```

The stats are projects shipped, pitches sent, reply rate (pitches that got at least one reply, divided by pitches sent) and total earned.

Privacy: the public page shows a pitch's date and channel only. The recipient appears only if you pass `--public-label`.

The seed holds only the two projects above and $0 earned. Everything else you log yourself.

## Tested

The built-in self-test (7 tests) passes. It covers the seed, exact money math, reply-rate counting, earnings totals, hiding pitch recipients and HTML escaping on the page, date validation, and a full command-line round trip.

Not tested: the page in a real browser.
