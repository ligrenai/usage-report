"""Codex CLI provider: reads rollout-*.jsonl under <CODEX_HOME>/sessions/YYYY/MM/DD/ (read-only).

Per-request tokens: `token_usage_record` events (codex >= 0.15x). Older rollouts: deltas of
`token_count.info.total_token_usage` between consecutive events (verified equal where both exist).
Quota: `token_count.rate_limits.primary|secondary` samples whose window is the weekly one (>= 10000 min).
"""
import glob, json, os

NAME = 'codex'

def parse_homes(specs):
    homes = {}
    for spec in specs or []:
        label, path = (spec.split('=', 1) if '=' in spec else (None, spec))
        path = os.path.expanduser(path)
        homes[label or os.path.basename(path.rstrip(os.sep)) or path] = path
    return homes

def default_homes(args=None):
    home = os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex')
    return {os.path.basename(home.rstrip(os.sep)) or 'codex': home}

def expand_root(root, names=None):
    """A directory whose children are CODEX_HOMEs (multi-account layout) -> {child: path}."""
    root = os.path.expanduser(root); homes = {}
    if os.path.isdir(os.path.join(root, 'sessions')): return {os.path.basename(root.rstrip(os.sep)): root}
    for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if os.path.isdir(os.path.join(root, d, 'sessions')) and (not names or d in names): homes[d] = os.path.join(root, d)
    return homes

def _backfill(recs, first_rec, model):
    if first_rec is None or not model or model == '?': return
    for i in range(first_rec, len(recs)):
        if recs[i][2] == '?': recs[i] = recs[i][:2] + (model,) + recs[i][3:]

def scan(homes):
    recs = []; series = {}
    for acc, home in homes.items():
        series.setdefault(acc, [])
        first_rec = None; model = '?'
        for f in sorted(glob.glob(os.path.join(home, 'sessions', '*', '*', '*', 'rollout-*.jsonl'))):
            _backfill(recs, locals().get('first_rec'), locals().get('model'))
            raw = open(f, 'rb').read(); has_rec = b'"token_usage_record"' in raw
            model = '?'; prev = (0, 0, 0); first_rec = len(recs)   # records logged before the file's first turn_context get its model back-filled
            for line in raw.decode('utf-8', 'ignore').split('\n'):
                if '"turn_context"' in line and model == '?':
                    try: model = json.loads(line)['payload'].get('model') or '?'
                    except Exception: pass
                    continue
                if '"token_count"' in line:
                    try: j = json.loads(line)
                    except Exception: continue
                    p = j.get('payload', {})
                    if j.get('type') != 'event_msg' or p.get('type') != 'token_count': continue
                    for k in ('primary', 'secondary'):
                        rl = (p.get('rate_limits') or {}).get(k)
                        if rl and rl.get('used_percent') is not None and (rl.get('window_minutes') or 0) >= 10000 and rl.get('resets_at'):
                            series[acc].append((j['timestamp'], float(rl['used_percent']), int(rl['resets_at']), (p.get('rate_limits') or {}).get('plan_type') or '?'))
                    if not has_rec:
                        info = p.get('info') or {}; t = info.get('total_token_usage')
                        if t:
                            cur = (t['input_tokens'], t['cached_input_tokens'], t['output_tokens'])
                            i, c, o = cur[0] - prev[0], cur[1] - prev[1], cur[2] - prev[2]; prev = cur
                            if i > 0 or o > 0:
                                recs.append((j['timestamp'], acc, model, i, c, o, (info.get('last_token_usage') or {}).get('input_tokens', i)))
                    continue
                if has_rec and '"token_usage_record"' in line:
                    try: j = json.loads(line)
                    except Exception: continue
                    if j.get('type') != 'token_usage_record': continue
                    u = j['payload']['usage']
                    recs.append((j['timestamp'], acc, model, u['input_tokens'], u['cached_input_tokens'], u['output_tokens'], u['input_tokens']))
        _backfill(recs, first_rec, model)
    recs.sort()
    return recs, series
