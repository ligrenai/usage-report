import json
import tempfile
import unittest
from pathlib import Path

from scripts.providers.codex import scan


def event(timestamp, payload, event_type='event_msg'):
    return {'timestamp': timestamp, 'type': event_type, 'payload': payload}


def turn(timestamp, model):
    return event(timestamp, {'model': model}, 'turn_context')


def count(timestamp, total, last, model=None):
    payload = {
        'type': 'token_count',
        'info': {'total_token_usage': total, 'last_token_usage': last},
    }
    if model:
        payload['model'] = model
    return event(timestamp, payload)


def record(timestamp, input_tokens, cached, output, response_id=None):
    payload = {'usage': {
        'input_tokens': input_tokens,
        'cached_input_tokens': cached,
        'output_tokens': output,
    }}
    if response_id:
        payload['response_id'] = response_id
    return event(timestamp, payload, 'token_usage_record')


def session_meta(timestamp='2026-07-01T00:00:00Z', forked_from_id=None):
    payload = {'timestamp': timestamp}
    if forked_from_id:
        payload['forked_from_id'] = forked_from_id
    return event(timestamp, payload, 'session_meta')


def write_rollout(home, name, rows):
    path = Path(home) / 'sessions' / '2026' / '07' / '01' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')


class CodexProviderTests(unittest.TestCase):
    def scan_rows(self, rows):
        with tempfile.TemporaryDirectory() as temp:
            write_rollout(temp, 'rollout-test.jsonl', rows)
            records, _ = scan({'test': temp})
            return records

    def scan_files(self, files):
        with tempfile.TemporaryDirectory() as temp:
            for name, rows in files:
                write_rollout(temp, name, rows)
            records, _ = scan({'test': temp})
            return records

    def test_first_legacy_snapshot_does_not_recount_fork_baseline(self):
        rows = [
            turn('2026-07-01T00:00:00Z', 'gpt-5.6-sol'),
            count('2026-07-01T00:00:01Z',
                  {'input_tokens': 1000, 'cached_input_tokens': 900, 'output_tokens': 10},
                  {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0}),
            count('2026-07-01T00:00:02Z',
                  {'input_tokens': 1200, 'cached_input_tokens': 1100, 'output_tokens': 20},
                  {'input_tokens': 200, 'cached_input_tokens': 200, 'output_tokens': 10}),
        ]
        records = self.scan_rows(rows)
        self.assertEqual([(r[3], r[4], r[5]) for r in records], [(200, 200, 10)])

    def test_first_legacy_snapshot_keeps_current_usage_on_top_of_baseline(self):
        rows = [
            turn('2026-07-01T00:00:00Z', 'gpt-5.6-sol'),
            count('2026-07-01T00:00:01Z',
                  {'input_tokens': 1100, 'cached_input_tokens': 1000, 'output_tokens': 15},
                  {'input_tokens': 100, 'cached_input_tokens': 100, 'output_tokens': 5}),
            count('2026-07-01T00:00:02Z',
                  {'input_tokens': 1200, 'cached_input_tokens': 1100, 'output_tokens': 25},
                  {'input_tokens': 100, 'cached_input_tokens': 100, 'output_tokens': 10}),
        ]
        records = self.scan_rows(rows)
        self.assertEqual([(r[3], r[4], r[5]) for r in records], [(100, 100, 5), (100, 100, 10)])

    def test_mixed_format_keeps_legacy_history_and_avoids_overlap(self):
        rows = [
            turn('2026-07-01T00:00:00Z', 'gpt-5.6-sol'),
            count('2026-07-01T00:00:01Z',
                  {'input_tokens': 100, 'cached_input_tokens': 90, 'output_tokens': 5},
                  {'input_tokens': 100, 'cached_input_tokens': 90, 'output_tokens': 5}),
            count('2026-07-01T00:00:02Z',
                  {'input_tokens': 150, 'cached_input_tokens': 140, 'output_tokens': 8},
                  {'input_tokens': 50, 'cached_input_tokens': 50, 'output_tokens': 3}),
            record('2026-07-01T00:00:03Z', 30, 20, 2),
            count('2026-07-01T00:00:04Z',
                  {'input_tokens': 180, 'cached_input_tokens': 160, 'output_tokens': 10},
                  {'input_tokens': 30, 'cached_input_tokens': 20, 'output_tokens': 2}),
        ]
        records = self.scan_rows(rows)
        self.assertEqual([(r[3], r[4], r[5]) for r in records], [(100, 90, 5), (50, 50, 3), (30, 20, 2)])

    def test_forked_mixed_format_ignores_replayed_legacy_history(self):
        rows = [
            session_meta(forked_from_id='parent-session'),
            turn('2026-07-01T00:00:00Z', 'gpt-5.6-sol'),
            count('2026-07-01T00:00:01Z',
                  {'input_tokens': 1000000, 'cached_input_tokens': 900000, 'output_tokens': 1000},
                  {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0}),
            record('2026-07-01T00:00:02Z', 300, 200, 4),
            count('2026-07-01T00:00:03Z',
                  {'input_tokens': 1000300, 'cached_input_tokens': 900200, 'output_tokens': 1004},
                  {'input_tokens': 300, 'cached_input_tokens': 200, 'output_tokens': 4}),
        ]
        records = self.scan_rows(rows)
        self.assertEqual([(r[3], r[4], r[5]) for r in records], [(300, 200, 4)])

    def test_model_context_is_updated_for_later_turns(self):
        rows = [
            turn('2026-07-01T00:00:00Z', 'gpt-5.6-sol'),
            record('2026-07-01T00:00:01Z', 100, 90, 5),
            turn('2026-07-01T00:00:02Z', 'gpt-6-astra'),
            record('2026-07-01T00:00:03Z', 200, 180, 6),
        ]
        records = self.scan_rows(rows)
        self.assertEqual([r[2] for r in records], ['gpt-5.6-sol', 'gpt-6-astra'])

    def test_duplicate_response_ids_across_fork_logs_are_counted_once(self):
        parent_rows = [
            turn('2026-07-01T00:00:00Z', 'gpt-5.6-sol'),
            record('2026-07-01T00:00:01Z', 100, 90, 5, response_id='resp-shared'),
        ]
        child_rows = [
            session_meta(forked_from_id='parent-session'),
            turn('2026-07-01T00:01:00Z', 'gpt-5.6-sol'),
            record('2026-07-01T00:01:01Z', 100, 90, 5, response_id='resp-shared'),
            record('2026-07-01T00:01:02Z', 200, 180, 6, response_id='resp-child-only'),
        ]
        records = self.scan_files([
            ('rollout-parent.jsonl', parent_rows),
            ('rollout-child.jsonl', child_rows),
        ])
        self.assertEqual([(r[3], r[4], r[5]) for r in records], [(100, 90, 5), (200, 180, 6)])


if __name__ == '__main__':
    unittest.main()
