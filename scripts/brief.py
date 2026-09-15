#!/usr/bin/env python3
"""Turn out/usage.json into a Markdown data brief for a social-post chart (fed to an image generator, e.g. codex $imagegen).

Two chart variants, both: X = local calendar days, line = "full-weekly-quota API value" = USD / quota % x 100.
  --by model  (default) bars stacked per model key (billable tokens: [1m] weighted by long/short price ratio per token type)
  --by type             bars stacked by token type: read (uncached input), cache read, write (output)
Days are taken from usage.json['daily'] (bucketed at the --tz given to collect.py; run collect.py with --tz -7 for San
Francisco, 0 for UTC). Optional filters keep only the accounts/days that belong to complete windows.
"""
import argparse, collections, json, os, sys

def fmt_m(x): return f'{x/1e6:,.0f}'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', default=os.path.join(os.path.dirname(__file__), '..', 'out', 'usage.json'))
    ap.add_argument('--by', choices=('model', 'type'), default='model')
    ap.add_argument('--days', nargs='*', help='local days to include (YYYY-MM-DD); default every day in the file')
    ap.add_argument('--accounts', nargs='*', help='accounts to include (default all)')
    ap.add_argument('--day-accounts', nargs='*', metavar='DAY=acc1,acc2', help='per-day account whitelist, overrides --accounts for that day')
    ap.add_argument('--phase', nargs='*', metavar='DAY=label', help='label a day (e.g. "sol A", "astra"); used for the summary tiles')
    ap.add_argument('--split', metavar='YYYY-MM-DD', help='date of a model switch to mark on the X axis')
    ap.add_argument('--min-pct', type=float, default=5.0, help='days below this quota %% get no line value (default 5)')
    ap.add_argument('--tz-label', default=None, help='text for the time zone in the header (default from meta.tz_offset_hours)')
    ap.add_argument('--out', help='write the brief here (default stdout)')
    a = ap.parse_args()
    d = json.load(open(a.inp)); daily = d['daily']; meta = d['meta']
    tz = a.tz_label or f"UTC{meta.get('tz_offset_hours', 0):+d}"
    days = a.days or sorted(daily)
    day_acc = dict(s.split('=', 1) for s in (a.day_accounts or []))
    phase = dict(s.split('=', 1) for s in (a.phase or []))
    keys = []   # model keys in first-seen order, auto-review last
    rows = []
    for day in days:
        accs = day_acc[day].split(',') if day in day_acc else (a.accounts or sorted(daily.get(day, {})))
        by = collections.defaultdict(float); typ = collections.Counter(); pct = 0.0; usd = 0.0; raw = collections.Counter()
        for acc in accs:
            m = daily.get(day, {}).get(acc)
            if not m: continue
            pct += m.get('_usage_pct', 0.0)
            for k, v in m.items():
                if k == '_usage_pct': continue
                bill = v.get('billable_uncached', v['input'] - v['cached']) + v.get('billable_cached', v['cached']) + v.get('billable_output', v['output'])
                by[k] += bill; usd += v['usd']
                typ['read'] += v.get('billable_uncached', v['input'] - v['cached']); typ['cache'] += v.get('billable_cached', v['cached']); typ['write'] += v.get('billable_output', v['output'])
                raw['input'] += v['input']; raw['output'] += v['output']
                if k not in keys: keys.append(k)
        rows.append({'day': day, 'accounts': accs, 'by': by, 'typ': typ, 'pct': pct, 'usd': usd, 'raw': raw,
                     'line': usd / pct * 100 if pct >= a.min_pct else None, 'phase': phase.get(day, '')})
    keys = [k for k in keys if not k.startswith('codex-auto-review')] + [k for k in keys if k.startswith('codex-auto-review')]
    o = []
    o.append(f"# Data brief: daily billable tokens vs. \"one full weekly quota at API prices\" ({days[0]} .. {days[-1]}, {tz})\n")
    o.append(f"Source: local Codex CLI rollout logs ({meta['provider']}), accounts {', '.join(meta['accounts'])}. Days are local calendar days ({tz}). "
             "Billable tokens = uncached input (read) + cache read + output (write, incl. reasoning); requests above "
             f"{meta['long_context_threshold']:,} input tokens ([1m]) are weighted by long price / standard price per token type. "
             "USD = tokens x published API prices (long-context column for [1m]); API-equivalent value, not money paid. "
             "Quota % = weekly quota percentage consumed that day (sum over the listed accounts; >100 means a reset credit was used). "
             "Line = USD / quota % x 100 = what one full (100 %) weekly quota is worth at API prices, measured from that day's usage.\n")
    if a.split: o.append(f"Mark a vertical divider at {a.split} (model switch).\n")
    if a.by == 'model':
        o.append('## Chart rows. Bars = billable tokens (M) stacked per model key. Line = full-weekly-quota API value (USD).\n')
        o.append('| date | phase | accounts | ' + ' | '.join(f'{k} M' for k in keys) + ' | total M | quota % | USD | line USD |')
        o.append('|---|---|---|' + '---|' * len(keys) + '---|---|---|---|')
        for r in rows:
            o.append(f"| {r['day']} | {r['phase']} | {','.join(r['accounts'])} | " + ' | '.join(fmt_m(r['by'].get(k, 0)) for k in keys)
                     + f" | {fmt_m(sum(r['by'].values()))} | {r['pct']:.0f} | {r['usd']:,.0f} | {('$%s' % format(r['line'], ',.0f')) if r['line'] else 'n/a'} |")
    else:
        o.append('## Chart rows. Bars = billable tokens (M) stacked by type: read (uncached input), cache read, write (output). Line = full-weekly-quota API value (USD).\n')
        o.append('| date | phase | accounts | read M | cache read M | write M | total M | quota % | USD | line USD |')
        o.append('|---|---|---|---|---|---|---|---|---|---|')
        for r in rows:
            t = r['typ']
            o.append(f"| {r['day']} | {r['phase']} | {','.join(r['accounts'])} | {fmt_m(t['read'])} | {fmt_m(t['cache'])} | {t['write']/1e6:,.1f} | {fmt_m(sum(t.values()))} | {r['pct']:.0f} | {r['usd']:,.0f} | {('$%s' % format(r['line'], ',.0f')) if r['line'] else 'n/a'} |")
    o.append('\n## Summary tiles (weighted by quota %)\n')
    groups = collections.OrderedDict()
    for r in rows: groups.setdefault(r['phase'] or 'all days', []).append(r)
    if len(groups) > 1: groups['all days'] = rows
    for label, rs in groups.items():
        pct = sum(r['pct'] for r in rs); usd = sum(r['usd'] for r in rs); tok = sum(sum(r['by'].values()) for r in rs)
        if pct <= 0: continue
        o.append(f"- {label}: {len(rs)} days · billable tokens {fmt_m(tok)} M (raw input {sum(r['raw']['input'] for r in rs)/1e9:.2f} B, raw output {sum(r['raw']['output'] for r in rs)/1e6:.1f} M) · quota {pct:.0f} % · ${usd:,.0f} · full-weekly-quota value ${usd/pct*100:,.0f} · billable tokens per 1 % = {tok/pct/1e6:.1f} M")
    o.append('\nFooter text: "local Codex CLI logs · tokens of >272K-context requests weighted like the price list · USD = tokens x published API prices, not money paid · line = USD / quota % x 100"')
    txt = '\n'.join(o) + '\n'
    if a.out: open(a.out, 'w').write(txt); print('wrote', a.out)
    else: sys.stdout.write(txt)

if __name__ == '__main__': main()
