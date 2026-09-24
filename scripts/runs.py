#!/usr/bin/env python3
"""Read local Codex runs, Claude transcripts, and observed quota capacity."""

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

try:
    from .providers import codex as provider
except ImportError:  # direct script invocation
    from providers import codex as provider

MISSING = 'NOT-MEASURED'
CLAUDE_FIELDS = ('input_tokens', 'cache_read_input_tokens',
                 'cache_creation_input_tokens', 'output_tokens')
TOKEN_FIELDS = ('input', 'cached', 'output', 'uncached',
                'billable_uncached', 'billable_cached', 'billable_output')


def missing(reason):
    return {'value': MISSING, 'reason': reason}


def timestamp(value):
    return provider._parse_timestamp(value)


def stamp(value):
    return provider._format_timestamp(value) if value else None


def safe_file(path):
    path = Path(path).resolve()
    if path.name in {'auth.json', '.credentials.json', '.claude.json'} or not path.is_file():
        raise ValueError(f'not a permitted transcript or rollout: {path}')
    return path


def rows(path):
    with safe_file(path).open(encoding='utf-8') as source:
        for line in source:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def quota_samples(path):
    for row in rows(path):
        payload = row.get('payload') or {}
        if row.get('type') != 'event_msg' or payload.get('type') != 'token_count':
            continue
        when = timestamp(row.get('timestamp'))
        if not when:
            continue
        for kind in ('primary', 'secondary'):
            value = (payload.get('rate_limits') or {}).get(kind) or {}
            if value.get('used_percent') is None or value.get('resets_at') is None:
                continue
            try:
                minutes = int(value.get('window_minutes') or (300 if kind == 'primary' else 10080))
                yield kind, (when, float(value['used_percent']), int(value['resets_at']), minutes)
            except (ValueError, TypeError):
                continue


def snapshot(samples):
    if not samples:
        return missing('no rate-limit snapshot')
    first, last = samples[0], samples[-1]
    result = {'first': {'used_percent': first[1], 'resets_at': first[2], 'window_minutes': first[3]},
              'last': {'used_percent': last[1], 'resets_at': last[2], 'window_minutes': last[3]}}
    result['percent_used_delta'] = (round(last[1] - first[1], 4) if first[2:] == last[2:]
                                    else missing('first and last snapshots are different windows'))
    return result


def command_measure(path):
    first = last = None
    session_id = None
    models, efforts = set(), set()
    begins, noncommands, ended, intervals, problems = {}, set(), set(), [], []
    command_count = 0
    for row in rows(path):
        when = timestamp(row.get('timestamp'))
        if when:
            first = min(first, when) if first else when
            last = max(last, when) if last else when
        payload = row.get('payload') or {}
        typ = row.get('type')
        if typ == 'session_meta' and session_id is None:
            session_id = payload.get('id') or payload.get('session_id')
        if typ == 'turn_context':
            if payload.get('model'): models.add(payload['model'])
            if payload.get('effort'): efforts.add(payload['effort'])
        if typ != 'response_item':
            continue
        kind, call_id = payload.get('type'), payload.get('call_id')
        if kind in ('function_call', 'custom_tool_call'):
            name = payload.get('name') or ''
            is_command = name in {'exec', 'exec_command', 'write_stdin', 'wait'} or name.endswith(('exec_command', '__exec', '__write_stdin', '__wait'))
            if is_command: command_count += 1
            if not call_id:
                if is_command: problems.append('begin lacks a unique call_id')
            elif call_id in begins or call_id in noncommands or call_id in ended:
                problems.append('begin lacks a unique call_id')
            elif is_command:
                begins[call_id] = when
            else:
                noncommands.add(call_id)
        elif kind in ('function_call_output', 'custom_tool_call_output'):
            if not call_id:
                continue
            if call_id in begins:
                start = begins.pop(call_id)
                ended.add(call_id)
                if start is None or when is None or when < start:
                    problems.append(f'invalid command interval: {call_id}')
                else:
                    intervals.append((start, when))
            elif call_id in noncommands:
                noncommands.remove(call_id)
                ended.add(call_id)
            else:
                problems.append(f'end lacks a unique begin: {call_id}')
    if begins: problems.append(f'{len(begins)} command begin event(s) lack an end event')
    if problems:
        busy = missing('; '.join(problems))
    else:
        busy = 0.0
        end = None
        for start, stop in sorted(intervals):
            if end is None or start > end:
                busy += (end - begin).total_seconds() if end else 0
                begin, end = start, stop
            else:
                end = max(end, stop)
        if end: busy += (end - begin).total_seconds()
        busy = round(busy, 3)
    return {'session_id': session_id or missing('no session metadata'),
            'models': sorted(models), 'efforts': sorted(efforts),
            'first_event_time': stamp(first) or missing('no timestamp'),
            'last_event_time': stamp(last) or missing('no timestamp'),
            'wall_clock_s': round((last - first).total_seconds(), 3) if first and last else missing('no timestamp'),
            'command_count': command_count, 'command_busy_union_s': busy}


def codex_run(path):
    if Path(path).is_symlink():
        raise ValueError(f'not a regular rollout file: {path}')
    path = safe_file(path)
    result = command_measure(path)
    records, _ = provider._scan({'run': str(path.parent)}, files={'run': [str(path)]},
                                session_root=str(path.parent))
    result['tokens'] = {'input': sum(r[3] for r in records),
                        'cached': sum(r[4] for r in records),
                        'output': sum(r[5] for r in records)}
    result['tokens']['uncached'] = result['tokens']['input'] - result['tokens']['cached']
    result['tokens']['total'] = result['tokens']['input'] + result['tokens']['output']
    samples = defaultdict(list)
    for kind, sample in quota_samples(path): samples[kind].append(sample)
    result['rate_limits'] = {kind: snapshot(sorted(samples[kind])) for kind in ('primary', 'secondary')}
    return result


def claude_run(path):
    messages = {}; models = set(); efforts = set(); compactions = 0
    first = last = None; block_sum = 0
    for row in rows(path):
        when = timestamp(row.get('timestamp'))
        if when:
            first = min(first, when) if first else when
            last = max(last, when) if last else when
        if row.get('type') == 'system' and row.get('subtype') == 'compact_boundary': compactions += 1
        for source in (row, row.get('message') or {}):
            for field in ('effort', 'perTurnEffort', 'reasoning_effort'):
                if isinstance(source.get(field), str) and source[field]: efforts.add(source[field])
        if row.get('type') != 'assistant' or not isinstance(row.get('message'), dict): continue
        message = row['message']
        if message.get('model'): models.add(message['model'])
        usage = message.get('usage')
        if not isinstance(usage, dict): continue
        block_sum += usage.get('output_tokens') or 0
        ident = message.get('id')
        if not ident: continue
        current = messages.setdefault(ident, {field: 0 for field in CLAUDE_FIELDS})
        for field in CLAUDE_FIELDS:
            value = usage.get(field) or 0
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f'invalid Claude usage {field}')
            current[field] = max(current[field], value)
    return {'unique_api_messages': len(messages), 'models': sorted(models),
            'efforts': sorted(efforts), 'compactions': compactions,
            'first_timestamp': stamp(first) or missing('no timestamp'),
            'last_timestamp': stamp(last) or missing('no timestamp'),
            'block_sum_output_tokens': block_sum,
            'usage': {field: sum(m[field] for m in messages.values()) for field in CLAUDE_FIELDS}}


def billable(record, prices):
    _, _, model, input_tokens, cached, output, size, *_ = record
    model_prices = prices['models'].get(model) or prices['models'][prices['fallback_model']]
    short = model_prices['short']
    long = model_prices.get('long') or short
    selected = long if size > prices['long_context_threshold'] else short
    weight = lambda field: selected.get(field, 0) / short[field] if short.get(field) else 1.0
    return {'input': input_tokens, 'cached': cached, 'output': output,
            'uncached': input_tokens - cached,
            'billable_uncached': (input_tokens - cached) * weight('input'),
            'billable_cached': cached * weight('cached'),
            'billable_output': output * weight('output')}


def capacity(homes, prices):
    result = {}
    for account, home in homes.items():
        samples = defaultdict(lambda: defaultdict(list))
        def receive_quota(_account, time, limits):
            when = timestamp(time)
            if not when: return
            for slot in ('primary', 'secondary'):
                value = limits.get(slot) or {}
                if value.get('used_percent') is None or value.get('resets_at') is None: continue
                try:
                    minutes = int(value.get('window_minutes') or (300 if slot == 'primary' else 10080))
                    kind = 'weekly' if minutes >= 10000 else 'five_hour' if minutes == 300 else None
                    if kind:
                        reset = int(value['resets_at']) // 600 * 600
                        samples[kind][reset].append((when, float(value['used_percent']), reset, minutes))
                except (TypeError, ValueError):
                    continue
        records, _ = provider.scan({account: home}, include_effort=True,
                                   quota_callback=receive_quota)
        timed_records = sorted((timestamp(record[0]), record) for record in records if timestamp(record[0]))
        record_times = [item[0] for item in timed_records]
        windows = []
        for kind in ('five_hour', 'weekly'):
            ordered = []
            for reset, group in samples[kind].items():
                group.sort()
                ordered.append((group[0][0], group[-1][0], reset, group))
            ordered.sort()
            for index, (start, end, reset, group) in enumerate(ordered):
                next_start = ordered[index + 1][0] if index + 1 < len(ordered) else None
                # The sampled interval is the only period attributable to this window.
                upper = min(end, next_start) if next_start else end
                peak = max(item[1] for item in group)
                consumed = peak - group[0][1]
                by = defaultdict(lambda: {'samples': 0, **{field: 0 for field in TOKEN_FIELDS}})
                low = bisect_left(record_times, start)
                high = (bisect_left(record_times, next_start)
                        if next_start is not None and next_start <= end
                        else bisect_right(record_times, upper))
                for _, record in timed_records[low:high]:
                    key = (record[2], record[9])
                    bucket = by[key]; bucket['samples'] += 1
                    for field, value in billable(record, prices).items(): bucket[field] += value
                groups = []
                for (model, effort), totals in sorted(by.items()):
                    per_pct = ({field: round(totals[field] / consumed, 3) for field in TOKEN_FIELDS}
                               if consumed > 0 else missing('window has no observed quota increase'))
                    groups.append({'model': model, 'effort': effort, **totals, 'per_1_percent': per_pct})
                windows.append({'kind': kind,
                                'resets_at': reset, 'first_sample_time': stamp(start),
                                'last_sample_time': stamp(end), 'quota_samples': len(group),
                                'start_used_percent': group[0][1], 'peak_used_percent': peak,
                                'consumed_percent': round(consumed, 4),
                                'partial': group[0][1] > 0 or peak < 100,
                                'by_model_effort': groups})
        result[account] = sorted(windows, key=lambda w: (w['resets_at'], w['kind']))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('codex', 'claude'):
        sub.add_parser(name).add_argument('files', nargs='+')
    cap = sub.add_parser('capacity')
    cap.add_argument('--home', nargs='+', required=True, metavar='LABEL=CODEX_HOME')
    args = parser.parse_args(argv)
    try:
        if args.command == 'codex':
            output = [{'file': path, **codex_run(path)} for path in args.files]
        elif args.command == 'claude':
            output = [{'file': path, **claude_run(path)} for path in args.files]
        else:
            homes = provider.parse_homes(args.home)
            if len(homes) != len(args.home) or any('=' not in item for item in args.home):
                raise ValueError('each home needs a distinct LABEL=CODEX_HOME')
            try:
                from .collect import load_prices
            except ImportError:
                from collect import load_prices
            prices = load_prices(str(Path(__file__).resolve().parents[1] / 'prices.json'))
            output = capacity(homes, prices)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'runs.py: {exc}\n')
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
