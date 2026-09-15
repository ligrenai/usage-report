# Social-post chart: prompt templates for an image generator

Two variants share one pipeline: `collect.py` (choose `--tz`: -7 San Francisco, 0 UTC, 8 Taipei) → `brief.py` (Markdown
data brief, every number the image may contain) → hand the brief plus one of the prompts below to an image-capable agent
(codex CLI: `$imagegen`, built-in `image_gen` tool; never the API-key CLI fallback unless the user asks). The generator must
read the brief, put only its numbers in the image, read the image back and check every number, and regenerate at most twice.

Variant A (default) — daily, all models: `python3 scripts/brief.py --by model ...`
Variant B — daily, token types (read / cache read / write): `python3 scripts/brief.py --by type ...`

Both: X axis = local calendar days (break the axis where days are skipped), bars = billable tokens per day, line with dots
on a right axis = "full-weekly-quota API value" (USD ÷ quota % × 100), quota % printed under each date, an optional vertical
divider at a model switch, summary tiles per phase, one takeaway sentence, a small footer. Layout that was accepted:
chart on the left (~70 % width), tiles stacked on the right, takeaway box below the chart, footer at the bottom.

## Prompt A — daily, stacked per model (default)

```
Use $imagegen (built-in image_gen tool) to design ONE polished social-media infographic (landscape 1536×1024 PNG).
Read <BRIEF PATH>; every number must come from that file, nothing invented.
- Headline: "Codex daily token burn vs. what a full weekly quota is worth at API prices" · subline "<date range>, <time zone>".
- Combined chart, X axis = the dates in the brief in order (axis break "//" where days are skipped).
  Bars (left axis, "billable tokens, M") stacked per model key, one colour per model key (base model and its [1m] variant as
  two tones of the same colour; codex-auto-review last, grey); print the day's total on top of each bar ("478 M").
  Line with dots (right axis, "USD"): the "line USD" column, dark navy, each dot labelled ("$2,089"); right axis 0 – <max rounded up>.
  Under each date the day's quota % ("12 %"). Vertical divider at <split date> labelled "<split date>: main model switched to <model>".
- Summary tiles on the right, one per phase in the brief: "<phase> · N days": full weekly quota ≈ $<value> · <tokens per 1 %> M billable tokens per 1 % · <quota %> quota used · $<USD>.
- Takeaway box: one sentence from the brief.
- Footer, small: the footer text from the brief.
Style: modern editorial infographic, off-white flat background, generous whitespace, one bold sans-serif family, one colour
family per model (blue for the older model, orange for the newer), dark navy line and text, light grid lines, no gradients
behind text, no photos, no people, no logos, no 3D, no clip-art. Legible at 50 % zoom; ≤ 80 words of running text.
Process: generate, read the image back, check every number/label/word against the brief (bars with totals, line labels,
quota %, tiles, takeaway, footer); regenerate up to two times if anything is wrong or garbled and keep the best.
Save the final PNG as <OUT PATH> and write the final prompt plus verification notes to <OUT PATH>.report.md.
If image_gen is unavailable, do NOT use the CLI/API fallback; say so and stop.
```

## Prompt B — daily, stacked by token type

Same as Prompt A except the bars: "stacked per day in three segments — cache read (lightest tone, the big part), read =
uncached input (mid tone), write = output (darkest, thin); phase 1 days in blues, phase 2 days in oranges" and the legend
lists the six segment colours plus the line. Footer adds "tokens of >272K-context requests weighted like the price list
(×2 read/cache read, ×1.5 write)".

## Choosing the days (the part a human decides)

- Prefer days that belong to complete weekly windows (`cycles[]` with `complete: true`) so the line is stable; skip days whose
  quota % rose while local tokens are near zero (usage on another machine) — pass `--day-accounts DAY=acc1,acc2`.
- Label phases with `--phase DAY=label` (e.g. `sol A`, `sol B`, `astra`); tiles are computed per label.
- Days below `--min-pct` (default 5 %) get no line value.

Worked example (two full windows of the older model, then a week of the newer one; accounts renamed):

```
python3 scripts/collect.py --home accountA=/path/to/codex-home-a accountB=/path/to/codex-home-b accountC=/path/to/codex-home-c --account-from accountC=2026-09-08 \
  --since 2026-08-20 --until 2026-09-12 --tz -7 --out out-sf
python3 scripts/brief.py --in out-sf/usage.json --by type --split 2026-09-03 --tz-label "San Francisco time (UTC-7)" \
  --days 2026-08-20 2026-08-21 2026-08-22 2026-08-23 2026-08-31 2026-09-01 2026-09-02 2026-09-05 2026-09-06 2026-09-07 2026-09-08 2026-09-09 2026-09-10 2026-09-11 \
  --day-accounts 2026-08-20=accountA 2026-08-21=accountA 2026-08-22=accountA 2026-08-23=accountA 2026-08-31=accountA 2026-09-01=accountA 2026-09-02=accountA \
                 2026-09-05=accountA,accountB 2026-09-06=accountA,accountB 2026-09-07=accountA,accountB 2026-09-08=accountA,accountB 2026-09-09=accountB,accountC 2026-09-10=accountB 2026-09-11=accountB \
  --phase 2026-08-20="sol A" 2026-08-21="sol A" 2026-08-22="sol A" 2026-08-23="sol A" 2026-08-31="sol B" 2026-09-01="sol B" 2026-09-02="sol B" \
          2026-09-05=astra 2026-09-06=astra 2026-09-07=astra 2026-09-08=astra 2026-09-09=astra 2026-09-10=astra 2026-09-11=astra \
  --out .dispatch/data-brief.md
```
