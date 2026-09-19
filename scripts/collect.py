#!/usr/bin/env python3
"""Collect provider token usage and publish API plus subscription billing views -> out/usage.json

  daily  : per local day, per account, per model, short/long context split, API-equivalent USD and credits
  cycles : per account quota cycles (one weekly used_percent window each), same splits + USD/credits per 1 %

Time range: --since/--until, else daily = --last-days (default 14) and quota cycles = --cycle-days (default 30), ending today. Accounts: none given = the
provider's single default home (codex: $CODEX_HOME or ~/.codex); --home label=path ... for several.
"""
import argparse, collections, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from providers import PROVIDERS

def parse_ts(ts): return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))

def load_prices(path):
    p = json.load(open(path))
    ov = os.path.join(os.path.dirname(os.path.abspath(path)), 'prices.overrides.json')
    if os.path.exists(ov):
        o = json.load(open(ov))
        used = []
        for m, cols in o.get('models', {}).items():
            for cls, vals in cols.items():
                if not isinstance(vals, dict): continue
                slot = p['models'].setdefault(m, {})
                if slot.get(cls, {}).get('input') is None:   # fetched page wins; overrides only fill what the page does not publish
                    slot[cls] = dict(vals); used.append(f'{m}/{cls}')
        p['long_context_threshold'] = p.get('long_context_threshold') or o.get('long_context_threshold', 272000)
        p['_overrides'] = ov; p['_overrides_used'] = used
    return p


def load_subscription_prices(path):
    with open(path, encoding='utf-8') as source:
        return json.load(source)

def collect(args):
    prov = PROVIDERS[args.provider]
    prices = load_prices(args.prices)
    subscription = load_subscription_prices(args.subscription_prices)
    TH = prices['long_context_threshold']
    tz = datetime.timedelta(hours=args.tz)
    today = (datetime.datetime.utcnow() + tz).date()
    since = args.since or (today - datetime.timedelta(days=args.last_days)).isoformat()
    until = args.until or today.isoformat()
    cycle_since = args.since or (today - datetime.timedelta(days=args.cycle_days)).isoformat()
    if args.home: homes = prov.parse_homes(args.home)
    elif args.accounts_root: homes = prov.expand_root(args.accounts_root, args.accounts)
    else: homes = prov.default_homes(args)
    recs, series = prov.scan(homes)
    series = {acc: [(ts, used, int(resets) // 600 * 600, plan) for ts, used, resets, plan in s] for acc, s in series.items()}
    plans = {acc: (collections.Counter(x[3] for x in s).most_common(1) or [('?', 0)])[0][0] for acc, s in series.items()}
    def price(model, cls):
        m = prices['models'].get(model) or prices['models'][prices['fallback_model']]
        return m.get(cls) or m['short']
    def cost(model, cls, i, c, o):
        p = price(model, cls); return (i - c) / 1e6 * p.get('input', 0) + c / 1e6 * p.get('cached', 0) + o / 1e6 * p.get('output', 0)
    def subscription_model(model):
        return subscription['models'].get(model) or subscription['models'][subscription['fallback_model']]
    def credit_cost(model, i, c, o):
        p = subscription_model(model).get('standard', {})
        return (i - c) / 1e6 * p.get('input', 0) + c / 1e6 * p.get('cached', 0) + o / 1e6 * p.get('output', 0)
    def fast_multiplier(model):
        return float(subscription_model(model).get('fast_multiplier', 1.0))
    def api_reference_cost(model, i, c, o):
        """Price subscription usage at the current API Standard reference rates."""
        p = subscription.get('_api_reference_prices', {}).get(model)
        if not p:
            current = price(model, 'short')
            p = {field: current.get(field, 0) for field in ('input', 'cached', 'output')}
        return (i - c) / 1e6 * p.get('input', 0) + c / 1e6 * p.get('cached', 0) + o / 1e6 * p.get('output', 0)
    def empty_metrics():
        return {'input': 0, 'cached': 0, 'output': 0, 'requests': 0, 'usd': 0.0, 'usd_standard': 0.0,
                'credits_standard': 0.0, 'credits': 0.0, 'credits_fast': 0.0, 'api_usd_from_credits': 0.0,
                'billable_uncached': 0.0, 'billable_cached': 0.0, 'billable_output': 0.0,
                'fast_requests': 0, 'standard_requests': 0, 'unknown_requests': 0}
    def add_metrics(target, model, cls, i, c, o, tier):
        base_credits = credit_cost(model, i, c, o)
        multiplier = fast_multiplier(model) if tier == 'fast' else 1.0
        consumed_credits = base_credits * multiplier
        target['input'] += i; target['cached'] += c; target['output'] += o; target['requests'] += 1
        target['usd'] += cost(model, cls, i, c, o); target['usd_standard'] += cost(model, 'short', i, c, o)
        target['credits_standard'] += base_credits; target['credits'] += consumed_credits
        target['credits_fast'] += consumed_credits if tier == 'fast' else 0.0
        target['api_usd_from_credits'] += api_reference_cost(model, i, c, o) * multiplier
        target[f'{tier}_requests'] += 1
        # Billable tokens: long-context tokens weighted by long/short price per token type.
        ps, pl = price(model, 'short'), price(model, cls)
        w = lambda f: (pl.get(f, 0) / ps.get(f)) if ps.get(f) else 1.0
        target['billable_uncached'] += (i - c) * w('input'); target['billable_cached'] += c * w('cached'); target['billable_output'] += o * w('output')
    def add(bucket, model, cls, i, c, o, tier):
        key = model if cls == 'short' else f'{model}[1m]'
        b = bucket.setdefault(key, {'model': model, 'context': cls, **empty_metrics()})
        add_metrics(b, model, cls, i, c, o, tier)
        tiers = bucket.setdefault('_service_tiers', {})
        add_metrics(tiers.setdefault(tier, empty_metrics()), model, cls, i, c, o, tier)
    acc_from = dict(s.split('=', 1) for s in (args.account_from or []))
    daily = collections.defaultdict(dict); hourly = collections.defaultdict(dict)
    tier_counts = collections.Counter()
    tier_source_counts = collections.Counter()
    for ts, acc, model, i, c, o, size, tier, tier_source in recs:
        d = (parse_ts(ts) + tz).strftime('%Y-%m-%d')
        if d < since or d > until or (acc in acc_from and d < acc_from[acc]): continue
        tier_counts[tier] += 1
        tier_source_counts[tier_source] += 1
        add(daily[d].setdefault(acc, {}), model, 'long' if size > TH else 'short', i, c, o, tier)
        add(hourly[parse_ts(ts).strftime('%Y-%m-%dT%H:00Z')].setdefault(acc, {}), model, 'long' if size > TH else 'short', i, c, o, tier)
    daily_pct = collections.defaultdict(lambda: collections.defaultdict(float)); hourly_pct = collections.defaultdict(lambda: collections.defaultdict(float))
    for acc, s in series.items():
        counts = collections.Counter(x[2] for x in s)
        runmax = {}   # per weekly window: running maximum of used_percent (session reports jitter by a few points)
        for ts, used, resets, plan in sorted(set(s)):
            d = (parse_ts(ts) + tz).strftime('%Y-%m-%d')
            if counts[resets] < args.min_samples: continue
            prev = runmax.get(resets)
            if prev is None: runmax[resets] = used; continue
            if used > prev:
                if since <= d <= until:
                    daily_pct[d][acc] += used - prev; hourly_pct[parse_ts(ts).strftime('%Y-%m-%dT%H:00Z')][acc] += used - prev
                runmax[resets] = used
    for d in daily:
        for acc in daily[d]: daily[d][acc]['_usage_pct'] = round(daily_pct[d].get(acc, 0.0), 1)
    for h in set(hourly) | set(hourly_pct):
        for acc in set(hourly[h]) | set(hourly_pct[h]): hourly[h].setdefault(acc, {})['_usage_pct'] = round(hourly_pct[h].get(acc, 0.0), 1)
    cycles = []
    for acc, s in series.items():
        s = sorted(set(s)); groups = collections.defaultdict(list)
        for x in s: groups[x[2]].append(x)
        gl = sorted([sorted(g) for g in groups.values() if len(g) >= args.min_samples], key=lambda g: g[0][0])
        for gi, g in enumerate(gl):
            nxt = gl[gi + 1][0][0] if gi + 1 < len(gl) else None
            seg = [x for x in g if nxt is None or x[0] < nxt]
            if len(seg) < 5: continue
            t0, t1 = seg[0][0], seg[-1][0]; d0 = parse_ts(t0) + tz; d1 = parse_ts(t1) + tz
            if d1.strftime('%Y-%m-%d') < cycle_since or d0.strftime('%Y-%m-%d') > until: continue
            if acc in acc_from and d0.strftime('%Y-%m-%d') < acc_from[acc]: continue
            peak = max(x[1] for x in seg); peak_ts = next(x[0] for x in seg if x[1] == peak)
            by = {}
            for ts, a, model, i, c, o, size, tier, tier_source in recs:
                if a == acc and t0 <= ts <= t1: add(by, model, 'long' if size > TH else 'short', i, c, o, tier)
            model_values = [v for k, v in by.items() if not k.startswith('_')]
            tin = sum(v['input'] for v in model_values)
            if tin < args.min_tokens: continue
            tout = sum(v['output'] for v in model_values); usd = sum(v['usd'] for v in model_values); usd_std = sum(v['usd_standard'] for v in model_values)
            credits = sum(v['credits'] for v in model_values); credits_std = sum(v['credits_standard'] for v in model_values); credits_fast = sum(v['credits_fast'] for v in model_values)
            credit_usd = sum(v['api_usd_from_credits'] for v in model_values)
            plan = collections.Counter(x[3] for x in seg).most_common(1)[0][0]
            consumed = peak - seg[0][1]
            cycles.append({'account': acc, 'plan': plan, 'start': d0.strftime('%Y-%m-%d %H:%M'), 'end': d1.strftime('%Y-%m-%d %H:%M'),
                           'start_utc': parse_ts(t0).strftime('%Y-%m-%dT%H:%MZ'), 'end_utc': parse_ts(t1).strftime('%Y-%m-%dT%H:%MZ'), 'peak_at_utc': parse_ts(peak_ts).strftime('%Y-%m-%dT%H:%MZ'),
                           'hours': round((d1 - d0).total_seconds() / 3600, 1), 'start_pct': seg[0][1], 'peak_pct': peak,
                           'peak_at': (parse_ts(peak_ts) + tz).strftime('%Y-%m-%d %H:%M'), 'end_pct': seg[-1][1],
                           'consumed_pct': round(consumed, 1), 'complete': peak >= args.complete_pct, 'input': tin, 'output': tout,
                           'usd': round(usd, 2), 'usd_per_pct': round(usd / max(consumed, 1), 2), 'usd_standard': round(usd_std, 2), 'usd_standard_per_pct': round(usd_std / max(consumed, 1), 2),
                           'credits': round(credits, 2), 'credits_per_pct': round(credits / max(consumed, 1), 2), 'credits_standard': round(credits_std, 2),
                           'credits_fast': round(credits_fast, 2), 'api_usd_from_credits': round(credit_usd, 2), 'api_usd_from_credits_per_pct': round(credit_usd / max(consumed, 1), 2), 'by_model': by,
                           'resets_at_utc': datetime.datetime.utcfromtimestamp(seg[0][2]).strftime('%Y-%m-%d %H:%M')})
    cycles.sort(key=lambda c: (c['account'], c['start']))
    # summary: what one full weekly window (100 %) is worth, per model family, from complete cycles dominated (>= 85 % of tokens) by one base model
    fam = collections.defaultdict(list)
    for c in cycles:
        if not c['complete'] or c['consumed_pct'] < 50: continue
        share = collections.Counter()
        for k, v in c['by_model'].items():
            if not k.startswith('_'): share[v['model']] += v['input']
        model, top = share.most_common(1)[0]
        if top / max(c['input'], 1) >= 0.75: fam[model].append(c)
    def window_stats(cs):
        n = len(cs); scale = [100.0 / c['consumed_pct'] for c in cs]   # normalise each window to a full 100 %
        return {'windows': n, 'accounts': sorted({c['account'] for c in cs}), 'cycle_ids': [f"{c['account']} {c['start']}" for c in cs],
                'avg_hours_per_window': round(sum(c['hours'] * k for c, k in zip(cs, scale)) / n, 1),
                'avg_input_per_window': round(sum(c['input'] * k for c, k in zip(cs, scale)) / n),
                'avg_output_per_window': round(sum(c['output'] * k for c, k in zip(cs, scale)) / n),
                'avg_usd_per_window': round(sum(c['usd'] * k for c, k in zip(cs, scale)) / n, 2),
                'avg_usd_standard_per_window': round(sum(c['usd_standard'] * k for c, k in zip(cs, scale)) / n, 2),
                'avg_credits_per_window': round(sum(c['credits'] * k for c, k in zip(cs, scale)) / n, 2),
                'avg_credits_standard_per_window': round(sum(c['credits_standard'] * k for c, k in zip(cs, scale)) / n, 2),
                'avg_credits_fast_per_window': round(sum(c['credits_fast'] * k for c, k in zip(cs, scale)) / n, 2),
                'avg_api_usd_from_credits_per_window': round(sum(c['api_usd_from_credits'] * k for c, k in zip(cs, scale)) / n, 2),
                'usd_standard_per_pct': round(sum(c['usd_standard_per_pct'] for c in cs) / n, 2),
                'plans': sorted({c['plan'] for c in cs}),
                'usd_per_pct': round(sum(c['usd_per_pct'] for c in cs) / n, 2),
                'input_per_pct': round(sum(c['input'] / c['consumed_pct'] for c in cs) / n),
                'long_share_of_input': round(sum(v['input'] for c in cs for k, v in c['by_model'].items() if not k.startswith('_') and v['context'] == 'long') / max(sum(c['input'] for c in cs), 1), 3)}
    eras = {}
    if args.era_split:
        for model, cs in fam.items():
            for era, sel in (('before', [c for c in cs if c['start'][:10] < args.era_split]), ('after', [c for c in cs if c['start'][:10] >= args.era_split])):
                if sel: eras[f'{era} {args.era_split} · {model}'] = dict(window_stats(sel), era=era, model=model, split=args.era_split)
    summary = {}
    for model, cs in fam.items():
        summary[model] = window_stats(cs)
    out = {'meta': {'provider': args.provider, 'generated': (datetime.datetime.utcnow() + tz).strftime('%Y-%m-%d %H:%M'), 'tz_offset_hours': args.tz,
                    'accounts': sorted(homes), 'homes': ({k: '<redacted>' for k in homes} if args.redact_homes else homes), 'plans': plans, 'since': since, 'until': until, 'cycle_since': cycle_since, 'account_from': acc_from,
                    'long_context_threshold': TH, 'prices': prices['models'], 'prices_source': prices.get('_source'), 'prices_fetched_at': prices.get('_fetched_at'),
                    'prices_overrides': prices.get('_overrides'), 'prices_overrides_used': prices.get('_overrides_used'), 'complete_pct': args.complete_pct,
                    'subscription_prices': subscription['models'], 'subscription_prices_source': subscription.get('_source'), 'subscription_prices_fetched_at': subscription.get('_fetched_at'),
                    'credits_per_api_usd': subscription['_credits_per_api_usd'], 'api_equivalent_basis': subscription.get('_api_equivalent_basis', 'current_api_price'),
                    'api_reference_prices': subscription.get('_api_reference_prices', {}), 'api_reference_note': subscription.get('_api_reference_note'),
                    'service_tier_counts': dict(tier_counts), 'service_tier_source_counts': dict(tier_source_counts),
                    'notes': ['tokens come only from files on this machine; usage elsewhere is invisible',
                              'input includes cached; uncached = input - cached; output includes reasoning',
                              'cache writes are not counted (no counter in the source files)',
                              'cycle = one weekly used_percent window (grouped by resets_at); complete = peak >= complete_pct',
                              'long context = request input > threshold, priced at the long column and keyed as <model>[1m]',
                              'daily _usage_pct = weekly quota percentage consumed that day per account (sum of used_percent increases)',
                              'daily is bucketed at tz_offset_hours (default 0 = UTC); hourly is UTC (keys YYYY-MM-DDTHH:00Z) so a viewer can re-bucket into local days',
                              'cycle start/end/peak_at are at tz_offset_hours; *_utc fields are UTC ISO',
                              'usd_standard = the same tokens priced at the standard (short-context) column, ignoring the long-context surcharge',
                              'credits_standard = published subscription credits at standard speed; credits = estimated subscription credits after the observed Fast multiplier',
                              'credits_fast = the estimated credits attributable to Fast/priority records; _service_tiers splits standard, fast, and unknown records',
                              'api_usd_from_credits = subscription credits mapped to the current API Standard reference prices, with the observed subscription Fast multiplier; this is approximate, not an official subscription billing rule or subscription money paid',
                              'service_tier is read directly when present, otherwise inferred from thread_settings_applied; unknown tiers are priced at standard speed',
                              'billable_* = tokens weighted by long price / short price per token type for [1m] buckets (weight 1 for short buckets); use these for token charts that should follow the pricing rule',
                              'plan = ChatGPT plan_type reported by the CLI for that account/cycle (pro, prolite, plus); quota sizes differ per plan']},
           'summary': {'per_model_full_window': summary, 'per_era_full_window': eras, 'method': 'complete cycles (peak >= complete_pct, consumed >= 50 pts) whose top base model holds >= 75 % of input tokens; each window scaled to 100 %'},
           'daily': {d: daily[d] for d in sorted(daily)}, 'hourly': {h: hourly[h] for h in sorted(hourly)}, 'cycles': cycles}
    os.makedirs(args.out, exist_ok=True)
    json.dump(out, open(os.path.join(args.out, 'usage.json'), 'w'), indent=1, ensure_ascii=False)
    return out

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--provider', default='codex', choices=sorted(PROVIDERS))
    ap.add_argument('--home', nargs='*', metavar='[LABEL=]PATH', help='provider home dirs (codex: CODEX_HOME). One = single account; several = multi-account. Default: provider default')
    ap.add_argument('--accounts-root', help='directory whose children are provider homes (multi-account layout)')
    ap.add_argument('--accounts', nargs='*', help='with --accounts-root: child names to include')
    ap.add_argument('--since'); ap.add_argument('--until'); ap.add_argument('--last-days', type=int, default=14, help='daily range when --since is absent (default 14)')
    ap.add_argument('--cycle-days', type=int, default=30, help='quota-cycle range when --since is absent (default 30)')
    ap.add_argument('--account-from', nargs='*', metavar='LABEL=YYYY-MM-DD', help='ignore an account before a date')
    ap.add_argument('--tz', type=int, default=0, help='day-bucket offset in hours for daily/cycle text fields (default 0 = UTC; hourly is always UTC)')
    ap.add_argument('--prices', default=os.path.join(here, '..', 'prices.json'))
    ap.add_argument('--subscription-prices', default=os.path.join(here, '..', 'prices.subscription.json'), help='published ChatGPT/Codex credit rates and Fast multipliers')
    ap.add_argument('--out', default=os.path.join(here, '..', 'out'))
    ap.add_argument('--complete-pct', type=float, default=95.0)
    ap.add_argument('--redact-homes', action='store_true', help='do not write the home directory paths into usage.json (for a report you will publish)')
    ap.add_argument('--era-split', default=None, metavar='YYYY-MM-DD', help='also summarise complete windows before/after this date (by window start)')
    ap.add_argument('--min-samples', type=int, default=20); ap.add_argument('--min-tokens', type=int, default=20_000_000)
    args = ap.parse_args(); out = collect(args)
    print(f"provider {args.provider}  accounts {out['meta']['accounts']}  range {out['meta']['since']}..{out['meta']['until']}  days {len(out['daily'])}  cycles {len(out['cycles'])}")
    for c in out['cycles']:
        print(f"{c['account']:<6} {c['start'][5:]} -> {c['end'][5:]}  {c['hours']:>6}h  {c['start_pct']:>3.0f}->{c['peak_pct']:>3.0f}%  in {c['input']/1e9:5.2f}B out {c['output']/1e6:6.2f}M  ${c['usd']:>7,.0f}  {c['credits']:>7,.0f} cr  {'FULL' if c['complete'] else 'part'}")
if __name__ == '__main__': main()
