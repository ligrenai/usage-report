#!/usr/bin/env python3
"""Fetch API prices from https://developers.openai.com/api/docs/pricing and cache them as prices.json.

The page embeds its pricing tables as Astro component props (a nested [tag, value] array form).
We decode every table whose headings contain "Model" and "input", keep the short/long context
columns when present (GroupedPricingTable), and fall back to the plain 4-column table otherwise.
Usage: fetch_prices.py [--out prices.json] [--url ...] [--from-file saved.html]
"""
import argparse, datetime, html, json, os, re, sys, urllib.request

URL = 'https://developers.openai.com/api/docs/pricing'

def decode(node):
    """Astro serialized props: [0, x] = value x; [1, [items]] = list; plain dict/list/str otherwise."""
    if isinstance(node, list) and len(node) == 2 and node[0] in (0, 1) and (node[0] == 0 or isinstance(node[1], list)):
        return decode(node[1]) if node[0] == 1 else decode(node[1]) if isinstance(node[1], (list, dict)) else node[1]
    if isinstance(node, list): return [decode(x) for x in node]
    if isinstance(node, dict): return {k: decode(v) for k, v in node.items()}
    return node

def props_iter(page):
    for m in re.finditer(r'props="([^"]*)"', page):
        raw = html.unescape(m.group(1))
        if '"headings"' not in raw and '"groups"' not in raw and '"rows"' not in raw: continue
        try: yield decode(json.loads(raw))
        except Exception: continue

def label(x):
    if isinstance(x, dict):
        for v in x.values():
            if isinstance(v, dict) and 'label' in v: return str(v['label'])
        return json.dumps(x)
    return str(x)

def num(v):
    try: return float(v)
    except Exception: return None

def clean_name(name):
    name = re.sub(r'<[^>]+>', ' ', name)
    base = re.sub(r'\s*\(.*?\)\s*$', '', name).strip()
    return base.split()[0] if base else base, ('>' in name and 'context' in name)

def parse(page, threshold=272_000):
    out = {}
    def put(model, cls, vals):
        e = out.setdefault(model, {}).setdefault(cls, {})
        for k, v in vals.items():
            if v is not None and k not in e: e[k] = v
    for props in props_iter(page):
        tier = str(props.get('tier') or 'standard').lower()
        if tier != 'standard': continue          # skip priority / flex / batch tables
        labels = [label(h) for h in (props.get('headingLabels') or props.get('headings') or [])]
        ll = [l.lower() for l in labels]
        # shape A: GroupedPricingTable  groups=[{model, rows:[[short in, cached, cache write, out, long in, cached, cache write, out]]}]
        if props.get('groups') and isinstance(props['groups'], list):
            width = len(ll) - 1 if ll and ll[0].lower() == 'model' else 8
            for g in props['groups']:
                if not isinstance(g, dict) or 'model' not in g: continue
                model, _ = clean_name(label(g['model']))
                row = (g.get('rows') or [[]])[0]
                if not isinstance(row, list): continue
                if width >= 8 and len(row) >= 8:
                    put(model, 'short', {'input': num(row[0]), 'cached': num(row[1]), 'cache_write': num(row[2]), 'output': num(row[3])})
                    put(model, 'long', {'input': num(row[4]), 'cached': num(row[5]), 'cache_write': num(row[6]), 'output': num(row[7])})
                elif len(row) >= 4:
                    put(model, 'short', {'input': num(row[0]), 'cached': num(row[1]), 'cache_write': num(row[2]), 'output': num(row[3])})
            continue
        # shape C: rows without headings  [name, input, cached, cache_write, output] or [name, input, cached, output]
        if props.get('rows') and not (props.get('headings') or props.get('headingLabels')):
            for row in props['rows']:
                if not isinstance(row, list) or not row or isinstance(row[0], (int, float)): continue
                model, long_ctx = clean_name(label(row[0]))
                if not model.startswith(('gpt', 'o')): continue
                nums = row[1:]
                if len(nums) >= 4: vals = {'input': num(nums[0]), 'cached': num(nums[1]), 'cache_write': num(nums[2]), 'output': num(nums[3])}
                elif len(nums) == 3: vals = {'input': num(nums[0]), 'cached': num(nums[1]), 'output': num(nums[2])}
                else: continue
                if vals['input'] is None: continue
                put(model, 'long' if long_ctx else 'short', vals)
            continue
        # shape B: plain table  headings=[Model, Input, Cached input, Cache writes, Output] rows=[[name, ...]]
        rows = props.get('rows')
        if not rows or not ll or ll[0] != 'model': continue
        def col(pred):
            for i, h in enumerate(ll):
                if pred(h): return i
            return None
        ci = col(lambda h: 'input' in h and 'cached' not in h); cc = col(lambda h: 'cached' in h)
        cw = col(lambda h: 'cache write' in h); co = col(lambda h: h.startswith('output'))
        if ci is None or co is None: continue
        for row in rows:
            if not isinstance(row, list) or not row or isinstance(row[0], (int, float)): continue
            model, long_ctx = clean_name(label(row[0]))
            if not model.startswith(('gpt', 'o')): continue
            vals = {'input': num(row[ci]) if ci < len(row) else None, 'cached': num(row[cc]) if cc is not None and cc < len(row) else None,
                    'cache_write': num(row[cw]) if cw is not None and cw < len(row) else None, 'output': num(row[co]) if co < len(row) else None}
            if vals['input'] is None: continue
            put(model, 'long' if long_ctx else 'short', vals)
    models = {m: v for m, v in out.items() if v.get('short', {}).get('input') is not None}
    for m, v in models.items():
        if not v.get('long', {}).get('input'): v.pop('long', None)   # no long-context price published: leave absent (overrides may fill it; collect.py falls back to short)
    return {'_source': URL, '_fetched_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ'),
            '_unit': 'USD per 1M tokens; long = request input above long_context_threshold',
            'long_context_threshold': threshold, 'fallback_model': 'gpt-5.6-sol' if 'gpt-5.6-sol' in models else sorted(models)[0], 'models': models}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument('--out', default=os.path.join(here, '..', 'prices.json'))
    ap.add_argument('--url', default=URL); ap.add_argument('--from-file')
    a = ap.parse_args()
    if a.from_file: page = open(a.from_file, errors='ignore').read()
    else:
        req = urllib.request.Request(a.url, headers={'User-Agent': 'Mozilla/5.0 usage-report'})
        page = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'ignore')
    data = parse(page)
    if not data['models']: print('no pricing table found; keeping existing prices.json', file=sys.stderr); sys.exit(1)
    json.dump(data, open(a.out, 'w'), indent=1); print(f"{len(data['models'])} models -> {a.out}")
    for m in ('gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'):
        if m in data['models']: print(' ', m, data['models'][m])
if __name__ == '__main__': main()
