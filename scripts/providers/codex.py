"""Codex CLI provider: reads rollout-*.jsonl under <CODEX_HOME>/sessions/YYYY/MM/DD/ (read-only).

Per-request tokens: `token_usage_record` events (codex >= 0.15x). Older rollouts use
`token_count.info.total_token_usage` deltas, while treating the first snapshot as a
possibly inherited fork baseline. A file can contain both formats during an upgrade:
legacy events before the first usage record are retained, and overlapping legacy events
after that transition are ignored. Reliable records are de-duplicated by `response_id`
across rollout files because forked children can replay parent records with new timestamps.
Records also carry the observed service tier (`standard`, `fast`, or `unknown`) and its
source. Historical `priority` settings are normalized to `fast`; when the usage event
does not carry a tier, the surrounding `thread_settings_applied` timeline is used.
Quota: `token_count.rate_limits.primary|secondary` samples whose window is the weekly one (>= 10000 min).
Some forked/subagent rollouts stamp every event with the file-creation time; those events
are re-timed to `task_started.started_at` when the outer timestamp is stale.
"""
import datetime
import glob, json, os
from collections import defaultdict

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

def _usage_tuple(value):
    value = value or {}
    return tuple(int(value.get(k) or 0) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'))


def _service_tier(value):
    """Normalize Codex's historical priority label to the current Fast name."""
    value = str(value or '').strip().lower()
    if value in ('fast', 'priority'):
        return 'fast'
    if value in ('standard', 'default'):
        return 'standard'
    return None


def _direct_service_tier(payload):
    """Read a tier if a future/current per-request event records one directly."""
    if not isinstance(payload, dict):
        return None
    for candidate in (
        payload.get('service_tier'),
        (payload.get('usage') or {}).get('service_tier'),
        (payload.get('metadata') or {}).get('service_tier'),
    ):
        tier = _service_tier(candidate)
        if tier:
            return tier
    return None


def _has_usage_fields(value):
    return isinstance(value, dict) and any(k in value for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'))


def _fill_unknown_model(events, model):
    if not model or model == '?': return events
    return [event[:2] + (model,) + event[3:] if event[2] == '?' else event for event in events]


def _parse_timestamp(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
        text = str(value).replace('Z', '+00:00')
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _format_timestamp(value):
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


def _effective_timestamp(timestamp, turn_start):
    """Repair rollout timestamps copied from the file-creation time.

    Some forked/subagent rollouts give every JSONL event the same outer
    timestamp. When that timestamp is materially away from the turn's own
    ``started_at``, use the turn start for attribution and quota ordering.
    """
    if not turn_start:
        return timestamp
    event_time = _parse_timestamp(timestamp)
    if event_time is None or abs((event_time - turn_start).total_seconds()) <= 3600:
        return timestamp
    return _format_timestamp(turn_start)

def scan(homes):
    recs = []; series = {}; seen_usage_ids = set(); seen_legacy_segments = set()
    for acc, home in homes.items():
        series.setdefault(acc, [])
        for f in sorted(glob.glob(os.path.join(home, 'sessions', '*', '*', '*', 'rollout-*.jsonl'))):
            model = '?'; first_model = '?'; prev = None; session_meta = {}
            active_tier = None
            legacy = []; legacy_by_tier = defaultdict(list); usage_records = []
            rows = []
            with open(f, 'rb') as fh:
                for raw_line in fh:
                    try: j = json.loads(raw_line)
                    except Exception: continue
                    rows.append(j)

            turn_starts = {}
            for j in rows:
                p = j.get('payload') or {}
                if j.get('type') == 'event_msg' and p.get('type') == 'task_started':
                    turn_id = p.get('turn_id')
                    started_at = _parse_timestamp(p.get('started_at'))
                    if turn_id and started_at:
                        turn_starts[turn_id] = started_at

            active_turn = None
            for j in rows:
                typ = j.get('type'); p = j.get('payload') or {}
                if typ == 'session_meta':
                    session_meta = p
                    continue
                if typ == 'event_msg' and p.get('type') == 'task_started':
                    active_turn = p.get('turn_id') or active_turn
                    continue
                if typ == 'event_msg' and p.get('type') == 'thread_settings_applied':
                    settings = p.get('thread_settings') or {}
                    tier = _service_tier(settings.get('service_tier'))
                    if tier:
                        active_tier = tier
                    continue
                if typ == 'turn_context':
                    candidate = p.get('model') or '?'
                    if candidate != '?':
                        if first_model == '?': first_model = candidate
                        model = candidate
                    continue
                turn_id = p.get('turn_id') or active_turn
                turn_start = turn_starts.get(turn_id)
                if not turn_start and len(turn_starts) == 1:
                    turn_start = next(iter(turn_starts.values()))
                timestamp = _effective_timestamp(j.get('timestamp'), turn_start)
                if typ == 'event_msg' and p.get('type') == 'token_count':
                    for k in ('primary', 'secondary'):
                        rl = (p.get('rate_limits') or {}).get(k)
                        if rl and rl.get('used_percent') is not None and (rl.get('window_minutes') or 0) >= 10000 and rl.get('resets_at'):
                            series[acc].append((timestamp, float(rl['used_percent']), int(rl['resets_at']), (p.get('rate_limits') or {}).get('plan_type') or '?'))
                    info = p.get('info') or {}; total = info.get('total_token_usage')
                    if not total: continue
                    cur = _usage_tuple(total)
                    last = info.get('last_token_usage')
                    last_present = _has_usage_fields(last)
                    last_usage = _usage_tuple(last)
                    if prev is None:
                        # A forked/resumed rollout often starts with an inherited total.
                        # The first event's last usage is the only new work we can attribute.
                        delta = last_usage if last_present else cur
                    elif any(cur[i] < prev[i] for i in range(3)):
                        # A reset starts a new cumulative segment; do not emit a negative delta.
                        delta = last_usage if last_present else cur
                    else:
                        delta = tuple(cur[i] - prev[i] for i in range(3))
                    prev = cur
                    i, c, o = delta
                    if i > 0 or o > 0:
                        size = int(last_usage[0] or i) if last_present else i
                        tier = _direct_service_tier(p) or active_tier or 'unknown'
                        source = 'direct' if _direct_service_tier(p) else ('timeline' if active_tier else 'unknown')
                        record = (timestamp, acc, model, i, c, o, size, tier, source)
                        legacy.append(record)
                        legacy_by_tier[tier].append(record)
                    continue
                if typ == 'token_usage_record':
                    response_id = p.get('response_id')
                    if response_id:
                        # A forked child can replay the parent's reliable usage records
                        # with a new timestamp. response_id is the stable request identity.
                        if response_id in seen_usage_ids:
                            continue
                        seen_usage_ids.add(response_id)
                    u = p.get('usage') or {}
                    input_tokens = int(u.get('input_tokens') or 0)
                    cached_input_tokens = int(u.get('cached_input_tokens') or 0)
                    output_tokens = int(u.get('output_tokens') or 0)
                    tier = _direct_service_tier(p) or active_tier or 'unknown'
                    source = 'direct' if _direct_service_tier(p) else ('timeline' if active_tier else 'unknown')
                    usage_records.append((timestamp, acc, model, input_tokens, cached_input_tokens, output_tokens, input_tokens, tier, source))
            legacy = _fill_unknown_model(legacy, first_model)
            usage_records = _fill_unknown_model(usage_records, first_model)
            # Forks created before reliable usage records can contain identical
            # legacy Fast/standard segments in sibling rollout files. Remove only
            # exact same-tier delta sequences from siblings sharing a parent id;
            # unrelated sessions and divergent branches remain untouched.
            fork_parent = session_meta.get('forked_from_id')
            if fork_parent and not usage_records:
                kept = []
                for tier, events in legacy_by_tier.items():
                    signature = tuple(event[3:6] for event in events)
                    marker = (acc, fork_parent, tier, signature)
                    if not signature or marker in seen_legacy_segments:
                        continue
                    seen_legacy_segments.add(marker)
                    kept.extend(_fill_unknown_model(events, first_model))
                legacy = kept
            if usage_records:
                if session_meta.get('forked_from_id'):
                    # Fork logs can replay the parent's historical token_count stream before
                    # emitting reliable per-request records. The parent log already owns that
                    # history; counting it here would charge the same work again.
                    recs.extend(usage_records)
                else:
                    first_record_ts = min(event[0] for event in usage_records)
                    # token_count continues to be emitted after token_usage_record was added.
                    # Keep the legacy history before the transition, but avoid double counting.
                    recs.extend(event for event in legacy if event[0] < first_record_ts)
                    recs.extend(usage_records)
            else:
                recs.extend(legacy)
    recs.sort()
    return recs, series
