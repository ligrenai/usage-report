---
name: usage-report
description: Price local Codex CLI usage at OpenAI API rates and ChatGPT/Codex subscription credits. Reads rollout jsonl from one or more CODEX_HOME dirs, splits tokens by model, context, and Standard/Fast service tier, rebuilds weekly quota cycles (0→100 %) per account, and renders a screenshot-ready HTML report.
---

# usage-report

Use when the user asks how many tokens Codex consumed, what that usage would cost at API prices or subscription credits,
what one weekly quota cycle is worth, or wants a chart of sol vs astra usage.

## Steps
1. Prices: `python3 scripts/fetch_prices.py` → refreshes `prices.json` from https://developers.openai.com/api/docs/pricing (standard tier; short/long context columns where published). Offline: keep the cached `prices.json` (or `prices.bundled.json`). `prices.overrides.json` only fills prices the page does not publish (e.g. long-context astra); the fetched page always wins. `meta.prices_overrides_used` in usage.json lists which entries were used; tell the user when any are.
2. Collect: `python3 scripts/collect.py` — single account by default (codex: `$CODEX_HOME` or `~/.codex`). Several accounts: `--home work=/path/to/codex-home-1 personal=/path/to/codex-home-2 ...` (each path is a CODEX_HOME, i.e. a directory with `sessions/`) (one label each) or `--accounts-root DIR [--accounts a b]` for a directory whose children are homes. Time: default daily = last 14 days, quota cycles = last 30 days; override with `--since/--until YYYY-MM-DD`, `--last-days N`, `--cycle-days N`. Other: `--tz 8`, `--subscription-prices prices.subscription.json`, `--account-from personal=2026-09-08` (ignore an account before a date, e.g. plan upgrade or usage on another machine), `--provider codex` (only provider today; add modules under `scripts/providers/`). Output `out/usage.json`. Read-only on source files.
3. Render: `python3 scripts/render.py [--theme dark]` → `out/report.html` (single file, no external assets). Open it in a browser and screenshot.
4. Report to the user: full cycles first (used % per cycle; USD per cycle and per 1 % of quota), then daily totals, then caveats.
5. Social-post chart (optional): `python3 scripts/brief.py --in out/usage.json [--by model|type] [--days …] [--day-accounts DAY=acc,…] [--phase DAY=label] [--split YYYY-MM-DD] --out .dispatch/data-brief.md` writes the only numbers the image may contain; then hand that brief plus a prompt from `references/imagegen-prompts.md` to an image-capable agent (codex `$imagegen`). Variant A (default) = daily bars stacked per model key; variant B = daily bars split into read / cache read / write. Both draw the "full-weekly-quota API value" line (USD ÷ quota % × 100). Run collect.py with the wanted `--tz` first (-7 San Francisco, 0 UTC). Verify every number in the returned image against the brief before publishing.

## Rules that keep the numbers honest
- Only rollouts on this machine are visible. If an account was also used elsewhere, say so; only cycles that ran 0→100 % locally are comparable.
- Cycle boundaries come from `rate_limits.primary.resets_at` (grouped, ≥20 samples per window). A second cycle that starts the same day is a separate row; accounts are never merged.
- Requests with input > 272K are priced at the long-context column (input and output) and keyed `<model>[1m]`. Token charts that should follow the pricing rule use the `billable_*` fields (long tokens weighted by long price ÷ standard price per token type); `usd_standard` is reference only.
- Plan tier (`plan_type` in the logs) is recorded in the JSON but not shown: it did not match the owner's records for every account.
- Subscription credits use the published standard credit table. Fast/priority is normalized and applies the model multiplier (2.5× for GPT-5.6/Astra/GPT-5.5 and 2× for GPT-5.4). Credit-to-API comparison uses original/list API reference rates, not promotional API rates: Sol is 20 credits per $1 at the supplied original `$5 / $0.50 / $25` rates; the default for other published models is 25. This is API-equivalent value only, not the subscription invoice amount; API Fast pricing is separate.
- Service tier is read directly when present, otherwise inferred from `thread_settings_applied`; unknown records are retained and priced at Standard, so Fast totals are a lower bound when historical tier evidence is missing.
- Times: collect.py buckets days at `--tz` (default 0 = UTC) and also emits UTC `hourly` buckets; the HTML re-buckets into the viewer's browser time zone.
- `input` includes cached; `output` includes reasoning; cache writes are not counted (rollouts carry no counter).
- Old rollouts (before codex wrote `token_usage_record`) are counted from deltas of `token_count.total_token_usage`; the first snapshot is baseline-safe for forked/resumed sessions, using `last_token_usage` when available. Files containing both formats keep legacy history before the first usage record and avoid counting overlapping `token_count` events afterward. Forked files with reliable usage records use those records alone because the child can replay the parent's historical token stream. Reliable records are de-duplicated by `response_id` across rollout files because a fork can replay the same request with a new timestamp.
- Fork siblings with legacy-only logs also discard identical same-tier delta sequences sharing one `forked_from_id`, while retaining divergent branches.
- Never call a provider CLI or API to measure quota; everything comes from files already on disk plus the public pricing page.
