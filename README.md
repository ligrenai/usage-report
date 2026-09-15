# usage-report

Turn local Codex CLI rollouts into an API-price-equivalent usage report: sol vs astra (or any model), per day and per weekly quota cycle, priced from the live OpenAI pricing page.

```
python3 scripts/fetch_prices.py                       # prices.json  <- developers.openai.com/api/docs/pricing (standard tier)
python3 scripts/collect.py                            # out/usage.json  single account ($CODEX_HOME or ~/.codex); daily 14 d, cycles 30 d
python3 scripts/render.py [--theme dark]              # out/report.html (self-contained; open and screenshot)
```

Multi-account example (this machine):
```
python3 scripts/collect.py --home work=/path/to/codex-home-1 personal=/path/to/codex-home-2 \
    --account-from personal=2026-09-08 --since 2026-09-01
```

Options: `--since/--until`, `--last-days 14` (daily), `--cycle-days 30` (quota cycles), `--tz 8`, `--provider codex` (providers live in `scripts/providers/`; only codex today).
```
```

Files
- `scripts/fetch_prices.py` — parses the pricing page's embedded tables (standard tier, short/long context). Cached in `prices.json`; `prices.bundled.json` is an offline fallback; `prices.overrides.json` is merged on top for prices the page does not publish.
- `scripts/providers/codex.py` — provider module (home discovery, rollout parsing); new providers register in `providers/__init__.py`.
- `scripts/collect.py` — read-only scan of `rollout-*.jsonl`; per-request tokens from `token_usage_record` (fallback: deltas of `token_count.total_token_usage`); quota cycles from `rate_limits.primary` (`used_percent`, `resets_at`).
- `scripts/render.py` — single-file HTML dashboard (SVG charts, tables), light or dark theme.
- `KEY-FIGURES.md` — reference measurements from 2026-09.

No dependencies beyond Python 3. Nothing is written outside this directory; rollouts are never modified.

## Render the dashboard

```bash
python3 scripts/render.py
python3 scripts/render.py --theme dark --out out/report-dark.html
python3 scripts/render.py --in out-acc3/usage.json --out out-acc3/report.html
python3 scripts/render.py --in out/usage.json --out out/report.html --title "Local usage report"
```

Open `out/report.html` directly (`file://` works). Each report is one HTML file,
with embedded JSON, CSS and JavaScript, no dependencies or external assets.
JavaScript is required. Light is the default theme; the page also has a theme toggle.
The default title is "Codex usage, valued at API prices". All interface text is in English.

The report covers the investigated period without an era comparison. The optional
`summary.per_model_full_window` block starts collapsed. Its cards show average USD,
input/output tokens, hours, USD and input per 1% quota, contributing accounts/window
counts, and long-context share. Each card shows the supplied summary for one model
across contributing accounts.
Qualifying complete cycles have peak quota at or above `complete_pct`, at least 50
consumed points, and one base model with at least 75% of input. Each window is scaled
to 100% before averaging by model. The optional social-post era summary is ignored entirely.

Dates and times are formatted in the viewer's browser time zone, identified once
in the header. Both the daily chart and table are built from UTC `hourly` buckets,
re-bucketed by local day; `meta.tz_offset_hours` and precomputed `daily` values do not
control the display. Cycle start/end/peak use their `*_utc` fields. The first and
last local day may be partial because the source range consists of UTC days.
Hourly buckets use their local start, so fractional-hour-offset zones retain only
hour-level precision at day boundaries. Older snapshots without hourly data and UTC
cycle timestamps must be recollected.

The overview shows period USD for each model key, complete-cycle medians by
dominant model family, and an account-switchable daily chart. Every model key,
including `[1m]`, has separate chart legend entries and daily/cycle table columns;
small models are never grouped into "other". `[1m]` uses a darker, hatched version
of the base model's colour. The quota line and total column show "quota % (sum over accounts)": daily
percentage points summed across accounts, or for the selected account.
Daily details place the date and existing account columns first, followed by
Observed total USD, quota %, and per-model input/output/USD groups. Auto-review
model groups come last; other models retain their order, with each base model
followed by its `[1m]` variant. Model groups with only zero or missing input,
output and USD are hidden for the displayed rows, recalculated when the account
selection changes. Cycle details apply the same empty-group rule to their rows.
Cycle details place Total USD and USD / 1% quota after the account/window/quota
and status columns, before the per-model input/output/USD groups; Reset time stays last.
All token labels use K (thousands, below 1 million), M (millions), or B (billions,
starting at 1 billion). Daily and cycle token cells, including daily totals, and
chart tooltip token labels expose raw counts with thousands separators only on hover.
Plan tier is not shown: the plan_type reported in the CLI logs did not match the owner's records for every account.
Optional `meta.plans` and `cycles[].plan` fields are ignored by the display.

Daily account USD is the sum of that account's local-day model bucket `usd` values.
Quota metadata and `usd_standard` are excluded; base and `[1m]` keys are each counted
once. The observed total sums accounts. Page `console.assert` checks reconcile each
day, each account, and the table footer with chart data. The previous renderer used
UTC `daily` dates directly, so its daily amounts did not describe browser-local days;
the audit found no quota-as-USD or base/long double counting in that calculation.

Cycle badges show `consumed_pct` and account headings identify accounts. A subtle check
marks cycles whose peak reaches `complete_pct`. Hover, focus, or tap a cycle for its
account, local interval/peak, hours, used percentage, total input/output, USD,
USD per 1%, and each model key's breakdown. Daily bars use the same tooltip
interactions; left/right arrows move between dates and Escape dismisses the tooltip.
Tables and prices remain in expandable sections, and motion respects reduced-motion
settings. Single-account mode hides the account switcher and identifies the account
in section headings.

To load current JSON when the HTML is served by a web server:

```bash
python3 scripts/render.py --data-url usage.json --out out/report.html
```

`--data-url URL` resolves relative to the HTML URL and fetches once at page load.
The embedded snapshot remains visible while loading and is used if the request
fails, times out, or returns invalid data. A retry button appears on failure.
Cross-origin URLs require the server to permit CORS; opening via `file://` may block
the fetch and use the embedded snapshot. Without this flag, the page makes no requests.

Weekly median dominance means the largest share of the cycle's USD by model family;
ties are listed separately. Medians use raw complete-cycle USD, including mixed
usage, with no extrapolation to 100%. Complete means
peak quota reached the threshold (normally ≥95%); observation need not start at 0%.
Cycle and daily ranges are independent. Resets can push daily consumption above
100%. Missing records display as gaps/`—`, not zero usage.

The pricing table has one row per observed model key. Columns show standard input,
cached input and output rates, plus applied long-context input/cached/output rates
for `[1m]` rows. Rates are per million tokens; recorded USD includes the long-context
surcharge, whereas `usd_standard` prices the same tokens at standard rates.
Unknown fallback rates are explicitly left unlisted rather than guessed.
The auto-review row is marked "priced at gpt-5.6-luna rates (owner decision)".


## Social-post chart (image generator)

```
python3 scripts/collect.py ... --tz -7 --since 2026-08-20 --until 2026-09-12 --out out-sf     # pick the time zone of the audience
python3 scripts/brief.py --in out-sf/usage.json --by model --split 2026-09-03 --out .dispatch/data-brief.md
```

`brief.py` writes a Markdown brief with one row per local day (billable tokens per model key, or per token type with `--by type`,
quota %, USD, and the line value = USD ÷ quota % × 100), summary tiles per `--phase` label, and the footer text. Give the brief
and a prompt from `references/imagegen-prompts.md` to an image-capable agent (codex CLI `$imagegen`); it must use only the brief's
numbers, read the image back and check them. Filters: `--days`, `--accounts`, `--day-accounts DAY=acc1,acc2`, `--min-pct`.
Fields used: `billable_uncached`, `billable_cached`, `billable_output` (long-context tokens weighted like the price list), `usd`, `_usage_pct`.

## Example report

`examples/report.html` is a rendered report (four accounts, September 2026, account names replaced, home paths redacted with
`collect.py --redact-homes`). Open it in a browser to see the layout before running the scripts on your own logs.

## License

Apache License 2.0 — Copyright 2026 Ligren, Inc. See `LICENSE` and `NOTICE`.
