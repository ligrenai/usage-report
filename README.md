# usage-report

Local Codex CLI usage, shown in OpenAI API value and ChatGPT/Codex subscription credits.

Price usage from local rollout files, rebuild weekly quota cycles per account,
render a self-contained HTML report, and write a data brief for a social-post chart.
Usage collection reads only files already on disk: no provider API calls, CLI
invocations, or quota polling. The API price fetcher downloads the public pricing
page; the bundled subscription snapshot records the published credit table and
Fast multipliers.
**USD means API-equivalent value, not money paid.**

**Python 3.9+ · Standard library only · [Apache-2.0](LICENSE)**

## Quick start

Run from the project directory. The default account uses `CODEX_HOME`, falling
back to `~/.codex`; its rollout files must already exist under `sessions/`.

```bash
python3 scripts/fetch_prices.py
python3 scripts/collect.py
python3 scripts/render.py
```

These write `prices.json`, `out/usage.json`, and `out/report.html`. Open the HTML
in a browser with JavaScript enabled; no web server is needed. For a preview,
open the included [example report](examples/report.html).

By default, daily data starts 14 days before today and cycles start 30 days
before today, with today included. The two ranges are independent.

### Multiple accounts

Give each home a distinct label. Each path is a Codex home containing `sessions/`.

```bash
python3 scripts/collect.py --home work=/path/to/codex-home personal=/path/to/codex-home-2
python3 scripts/render.py
```

Alternatively, use `--accounts-root` for a directory containing account homes,
with `--accounts` to select child directory names.

### Date range and time zone

Dates are inclusive. `--tz` is a fixed, whole-hour UTC offset; it controls the
collector's daily buckets and the social brief. The HTML uses the viewer's time zone.

```bash
python3 scripts/collect.py --since 2026-09-01 --until 2026-09-14 --tz 8
python3 scripts/render.py
```

For a report you will share, collect with `--redact-homes` before rendering:

```bash
python3 scripts/collect.py --redact-homes
python3 scripts/render.py --theme dark
```

This redacts `meta.homes`. Account labels and usage remain; `meta.prices_overrides`
can still contain a local path. Review the JSON and embedded report data before sharing.

### Common CLI flags

| Script | Flags | Purpose |
| --- | --- | --- |
| `collect.py` | `--home`, `--accounts-root`, `--accounts` | Select one or more account homes. |
| `collect.py` | `--since`, `--until` | Set inclusive date boundaries. Cycles keep their full observed intervals. |
| `collect.py` | `--last-days`, `--cycle-days` | Set daily/cycle lookback when `--since` is absent; defaults: 14/30. |
| `collect.py` | `--account-from` | Set an account's start date with `LABEL=YYYY-MM-DD`; see limitations below. |
| `collect.py` | `--tz` | Set the daily bucket UTC offset; default: 0. |
| `collect.py` | `--prices`, `--out`, `--redact-homes` | Select price JSON, output directory, and home-path redaction. |
| `collect.py` | `--subscription-prices` | Select the ChatGPT/Codex credit and Fast multiplier snapshot; defaults to `prices.subscription.json`. |
| `collect.py` | `--complete-pct`, `--min-samples`, `--min-tokens` | Cycle thresholds; defaults: 95%, 20 samples, 20 million input tokens. |
| `fetch_prices.py` | `--from-file`, `--out` | Parse a saved pricing page or choose the price JSON output. |
| `render.py` | `--in`, `--out`, `--title`, `--theme`, `--data-url` | Select JSON, HTML output, title, light/dark theme, or live JSON URL. |
| `brief.py` | `--by`, `--days`, `--accounts`, `--day-accounts`, `--phase`, `--split` | Choose chart variant, data filters, phase labels, and a model-switch marker. |

## How it works

### Local data sources

The Codex provider scans `sessions/YYYY/MM/DD/rollout-*.jsonl` under each home.
It reads per-request `token_usage_record` events. For older rollouts without
those events, it uses deltas of `token_count.info.total_token_usage`.

Quota samples come from `rate_limits.primary` or `rate_limits.secondary` when
`window_minutes` identifies a weekly window (at least 10,000 minutes). Cycles
are grouped per account by `resets_at`, rounded down to ten-minute boundaries.
Daily quota consumption sums increases in each window's running maximum.

Legacy `token_count` totals are cumulative snapshots. The first snapshot in a
rollout can inherit a large baseline from a fork or resumed session, so it is
not automatically counted as new usage; the collector uses its
`last_token_usage` contribution when available and deltas thereafter. During
the rollout format transition, a file may contain both `token_count` and
`token_usage_record`; legacy events before the first usage record are retained,
and overlapping legacy events after that point are ignored.
Forked files that contain reliable `token_usage_record` events use those records
alone, because Codex can replay the parent's historical `token_count` stream into
the child file. Reliable records are also de-duplicated by `response_id` across
rollout files because a fork can replay the same request with a new timestamp.
For older fork siblings that have only legacy counters, identical same-tier delta
segments sharing one `forked_from_id` are counted once. This removes only exact
replays; divergent branches are retained.

Each token record also carries `service_tier`: `standard`, `fast`, or `unknown`.
The historical `priority` setting is normalized to `fast`. A tier in the usage
event is preferred; otherwise the provider uses the surrounding
`thread_settings_applied` timeline. Records with no tier evidence are priced at
Standard and remain visible in the `unknown` breakdown.

### Pricing

- [scripts/fetch_prices.py](scripts/fetch_prices.py) extracts standard-tier tables
  from the OpenAI pricing page and caches short/long-context rates in `prices.json`.
- [prices.subscription.json](prices.subscription.json) stores the published
  subscription credit rates and model-specific Fast multipliers. The official
  subscription table maps to the current API Standard table at **25 credits per
  $1 of API-equivalent value** for the published models (minor rounding exists in
  some displayed credit rates). This is an analytical conversion, not the
  subscription invoice price; plan agreements and credit purchase discounts are
  separate.
- The official Fast rules are model-specific: GPT-5.6/Astra and GPT-5.5 use
  2.5× subscription credits, while GPT-5.4 uses 2×. API Fast/Priority pricing is
  separate and is never mixed into the subscription credit calculation.
- Requests with input **above 272,000 tokens** use the long-context column and the
  model key `<model>[1m]`. The threshold is stored in `long_context_threshold`.
- [prices.overrides.json](prices.overrides.json) fills unpublished model/context
  prices when that context has no input rate. Published contexts take precedence.
  Applied entries appear in `meta.prices_overrides_used`; the included overrides
  also price `codex-auto-review` at `gpt-5.6-luna` rates (no published rate exists).
- Missing long-context rates fall back to short-context rates. Unknown models
  use the price file's `fallback_model`; their fallback rates are not listed in
  the report because that identifier is not exported into usage metadata.
- `usd` prices uncached input, cached input, and output separately.
  `usd_standard` prices the same tokens at short-context rates.
  `billable_uncached`, `billable_cached`, and `billable_output` weight each token
  type by its long/short price ratio, so social-chart bars follow the pricing rule.
- `credits_standard` prices all tokens at the published subscription Standard rate;
  `credits` applies the observed Fast multiplier; `credits_fast` isolates the
  actual Fast/priority credit consumption; and `api_usd_from_credits` divides
  credits by `meta.credits_per_api_usd`.

To work offline, keep the cached prices or explicitly select the bundled snapshot:

```bash
python3 scripts/collect.py --prices prices.bundled.json
```

### HTML report

The report embeds JSON, CSS, JavaScript, SVG charts, and tables in one HTML file.
It includes period totals, daily usage, weekly quota cycles, complete-cycle
medians, subscription credit/Fast summaries, and expandable details and pricing
tables.

- Dates use the **viewer's browser time zone**, rebuilding local days from UTC
  `hourly` buckets. Edge days can be partial; fractional-hour zones have only
  hour-level precision at day boundaries. Older JSON without hourly buckets and
  UTC cycle timestamps must be recollected.
- Token labels use **K/M/B** units, with exact counts available on hover.
  Each model key, including `[1m]`, has separate columns; empty model groups hide.
- Multiple accounts have an account selector. Single-account mode hides it and
  identifies the account in headings. Light is the default; a theme toggle and
  `--theme dark` are available.
- Weekly medians use raw complete-cycle USD, including mixed-model usage.
  The optional `summary.per_model_full_window` section scales qualifying cycles
  to 100% before averaging: at least 50 consumed quota points and one base model
  responsible for at least 75% of input tokens.

For HTML served by a web server, fetch updated JSON once at page load:

```bash
python3 scripts/render.py --data-url usage.json --out out/report.html
```

The URL resolves relative to the HTML URL. The embedded snapshot remains the
fallback on failure. Cross-origin URLs require CORS; local file access may block
fetching. Without `--data-url`, the report makes no network requests.

## Output schema

`out/usage.json` has five top-level sections. Selected field names:

| Section | Fields / nesting |
| --- | --- |
| `meta` | `provider`, `generated`, `accounts`, `homes`, `plans`, `since`, `until`, `cycle_since`, `account_from`, `tz_offset_hours`, `long_context_threshold`, `prices`, `prices_source`, `prices_fetched_at`, `subscription_prices`, `subscription_prices_source`, `credits_per_api_usd`, `service_tier_counts`, `service_tier_source_counts`, `complete_pct`, `notes` |
| `daily` | date → account → model key; account-level `_usage_pct` |
| `hourly` | UTC hour → account → model key; account-level `_usage_pct` |
| `cycles` | `account`, `plan`, `start`, `end`, `start_utc`, `end_utc`, `peak_at`, `peak_at_utc`, `resets_at_utc`, `hours`, `start_pct`, `peak_pct`, `end_pct`, `consumed_pct`, `complete`, `input`, `output`, `usd`, `usd_per_pct`, `usd_standard`, `usd_standard_per_pct`, `credits`, `credits_per_pct`, `credits_standard`, `credits_fast`, `api_usd_from_credits`, `api_usd_from_credits_per_pct`, `by_model` |
| `summary` | `per_model_full_window`, `per_era_full_window`, `method` |

Model buckets in `daily`, `hourly`, and `cycles[].by_model` share:
`model`, `context`, `input`, `cached`, `output`, `requests`, `usd`, `usd_standard`,
`billable_uncached`, `billable_cached`, `billable_output`, `credits_standard`,
`credits`, `credits_fast`, `api_usd_from_credits`, `fast_requests`,
`standard_requests`, and `unknown_requests`. Account/day buckets and cycle
`by_model` maps also carry `_service_tiers` with the same aggregate fields.

## Social-post chart

Choose the audience's UTC offset when collecting, then generate a Markdown brief.
Create the output directory first; `brief.py` does not create it.

```bash
mkdir -p .dispatch
python3 scripts/brief.py --in out/usage.json --by model --out .dispatch/data-brief.md
```

**Variant A** (`--by model`, the default) stacks daily billable tokens by model key.
For **variant B**, stack them by read, cache read, and write (output):

```bash
python3 scripts/brief.py --in out/usage.json --by type --out .dispatch/data-brief.md
```

Both use the line **full-weekly-quota API value = USD ÷ quota % × 100**.
`--min-pct` suppresses line values below 5% by default. Use `--days`, `--accounts`,
and `--day-accounts` to select comparable observations; `--phase` labels summary
tiles and `--split` marks a model switch. `--tz-label` changes header text only.

Hand the brief and the matching [image-generator prompt](references/imagegen-prompts.md)
to an image-capable agent. Every number must come from the brief. Read the image
back and verify its numbers and labels before publishing.

## Use as a skill

Copy this entire project folder into your agent's skills directory, keeping
[SKILL.md](SKILL.md) at the folder root alongside the scripts, price files, and
references. The skill describes the collection, reporting, and chart handoff workflow.

## Accuracy and limitations

- **This machine only.** Usage on other machines is invisible. Compare complete
  cycles observed locally from 0% to 100%; a `complete` badge only means the observed
  peak reached `--complete-pct` (95% by default), even if observation began above 0%.
- Cycles retain their full observed intervals and can extend beyond the selected
  daily range. Sparse or low-token cycles are filtered by the cycle thresholds.
- `input` includes cached tokens; `output` includes reasoning tokens. Cache writes
  are not counted because rollout files provide no counter.
- Plan tier is recorded in JSON but hidden in the report because logged `plan_type`
  values were observed to disagree with the actual subscription tier.
- Service tier is not available on every historical request. Unknown records are
  shown and conservatively priced at Standard; Fast totals are therefore a lower
  bound for periods with missing tier evidence.
- Old rollouts use cumulative-total deltas with a fork-safe first snapshot;
  per-request attribution depends on the information available in those logs.
- `--account-from` filters token records and cycle starts, but currently does not
  filter daily/hourly quota samples. Quota percentages can therefore include earlier usage.
- Daily quota percentages sum across accounts and resets, so they can exceed 100%.
  The brief's extrapolated line is an estimate based on each selected day's usage.

## Providers

Only `codex` is supported today (`--provider codex`). To add a provider, create
its module under [scripts/providers/](scripts/providers/) and register its `NAME`
in `PROVIDERS` in [scripts/providers/__init__.py](scripts/providers/__init__.py).
Use [scripts/providers/codex.py](scripts/providers/codex.py) as the interface reference:

- `parse_homes(specs)`, `default_homes(args)`, `expand_root(root, names=None)` return
  a mapping of account labels to home paths.
- `scan(homes)` returns `(records, ratelimits)`. Records contain
  `(ts_iso_utc, account_label, model, input_tokens, cached_input_tokens, output_tokens, request_input_size, service_tier, tier_source)`.
  Rate limits map account labels to `(ts_iso_utc, used_percent, resets_at_epoch, plan)` samples.

## Contributing

Keep changes focused. Never commit `out/`, `.dispatch/`, real user paths, or private
rollout data. Use synthetic or redacted examples. Before opening a PR, compile the scripts:

```bash
python3 -m py_compile scripts/collect.py scripts/brief.py scripts/fetch_prices.py scripts/render.py scripts/providers/__init__.py scripts/providers/codex.py
```

## License

[Apache License 2.0](LICENSE). Copyright 2026 Ligren, Inc. See [NOTICE](NOTICE).
