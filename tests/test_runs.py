import json
import tempfile
import unittest
from pathlib import Path

from scripts import runs


def row(time, typ, payload):
    return {'timestamp': time, 'type': typ, 'payload': payload}


def write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(record) + '\n' for record in records))
    return path


class RunsTests(unittest.TestCase):
    def test_codex_union_and_shared_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rollout-one.jsonl'
            records = [row('2026-01-01T00:00:00Z', 'session_meta', {'id': 's1'}),
                       row('2026-01-01T00:00:00Z', 'turn_context', {'model': 'gpt-5.6-sol', 'effort': 'high'})]
            for ident, time in [('a', '00:00:01'), ('b', '00:00:02')]:
                records.append(row('2026-01-01T' + time + 'Z', 'response_item',
                                   {'type': 'function_call', 'name': 'exec_command', 'call_id': ident}))
            for ident, time in [('a', '00:00:04'), ('b', '00:00:05')]:
                records.append(row('2026-01-01T' + time + 'Z', 'response_item',
                                   {'type': 'function_call_output', 'call_id': ident}))
            records.append(row('2026-01-01T00:00:05Z', 'token_usage_record',
                               {'usage': {'input_tokens': 100, 'cached_input_tokens': 40, 'output_tokens': 10}}))
            for pct, time in [(20, '00:00:00'), (25, '00:00:05')]:
                records.append(row('2026-01-01T' + time + 'Z', 'event_msg',
                                   {'type': 'token_count', 'rate_limits': {
                                       'primary': {'used_percent': pct, 'resets_at': 12345}}}))
            result = runs.codex_run(write(path, records))
            self.assertEqual(result['command_busy_union_s'], 4)
            self.assertEqual(result['command_count'], 2)
            self.assertEqual(result['tokens']['total'], 110)
            self.assertEqual(result['rate_limits']['primary']['percent_used_delta'], 5)

    def test_unpaired_command_is_not_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(Path(directory) / 'rollout-one.jsonl', [
                row('2026-01-01T00:00:00Z', 'response_item',
                    {'type': 'function_call', 'name': 'exec_command', 'call_id': 'open'})])
            self.assertEqual(runs.codex_run(path)['command_busy_union_s']['value'], runs.MISSING)

    def test_tool_without_call_id_does_not_discard_command_busy_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(Path(directory) / 'rollout-one.jsonl', [
                row('2026-01-01T00:00:00Z', 'response_item',
                    {'type': 'function_call', 'name': 'exec_command', 'call_id': 'cmd'}),
                row('2026-01-01T00:00:01Z', 'response_item',
                    {'type': 'function_call', 'name': 'read_file'}),
                row('2026-01-01T00:00:03Z', 'response_item',
                    {'type': 'function_call_output', 'call_id': 'cmd'})])
            self.assertEqual(runs.command_measure(path)['command_busy_union_s'], 3)

    def test_command_without_call_id_is_not_measured(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(Path(directory) / 'rollout-one.jsonl', [
                row('2026-01-01T00:00:00Z', 'response_item',
                    {'type': 'function_call', 'name': 'exec_command'})])
            self.assertEqual(runs.command_measure(path)['command_busy_union_s']['value'], runs.MISSING)

    def test_single_rollout_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = write(Path(directory) / 'target.jsonl', [
                row('2026-01-01T00:00:00Z', 'token_usage_record',
                    {'usage': {'input_tokens': 1}})])
            link = Path(directory) / 'rollout-link.jsonl'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                runs.codex_run(link)

    def test_claude_message_max_and_block_sum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transcript.jsonl'
            records = []
            for output in (5, 8):
                records.append({'timestamp': '2026-01-01T00:00:00Z', 'type': 'assistant',
                                'effort': 'high', 'message': {'id': 'msg1', 'model': 'claude-test',
                                'usage': {'input_tokens': 100, 'output_tokens': output}}})
            records.append({'timestamp': '2026-01-01T00:00:01Z', 'type': 'system',
                            'subtype': 'compact_boundary'})
            result = runs.claude_run(write(path, records))
            self.assertEqual(result['unique_api_messages'], 1)
            self.assertEqual(result['usage']['output_tokens'], 8)
            self.assertEqual(result['block_sum_output_tokens'], 13)
            self.assertEqual(result['compactions'], 1)

    def test_claude_block_sum_includes_usage_without_message_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(Path(directory) / 'transcript.jsonl', [
                {'type': 'assistant', 'message': {'usage': {'output_tokens': 7}}},
                {'type': 'assistant', 'message': {'id': 'msg1',
                 'usage': {'output_tokens': 5}}}])
            result = runs.claude_run(path)
            self.assertEqual(result['block_sum_output_tokens'], 12)
            self.assertEqual(result['unique_api_messages'], 1)
            self.assertEqual(result['usage']['output_tokens'], 5)

    def test_claude_invalid_block_output_without_message_id_is_rejected(self):
        for bad in (-1, '7', True):
            with tempfile.TemporaryDirectory() as directory:
                path = write(Path(directory) / 'transcript.jsonl', [
                    {'type': 'assistant', 'message': {'usage': {'output_tokens': bad}}}])
                with self.assertRaises(ValueError):
                    runs.claude_run(path)

    def test_capacity_groups_windows_and_billable_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / 'sessions' / '2026' / '01' / '01' / 'rollout-one.jsonl'
            records = [row('2026-01-01T00:00:00Z', 'turn_context', {'model': 'gpt-5.6-sol', 'effort': 'high'})]
            for time, pct, reset in [('00:00:00', 0, 1000), ('00:00:02', 50, 1001),
                                     ('00:00:03', 0, 2000), ('00:00:05', 100, 2000)]:
                records.append(row('2026-01-01T' + time + 'Z', 'event_msg',
                                   {'type': 'token_count', 'rate_limits': {
                                       'primary': {'used_percent': pct, 'resets_at': reset}}}))
            for time in ('00:00:01', '00:00:04'):
                records.append(row('2026-01-01T' + time + 'Z', 'token_usage_record',
                                   {'usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10}}))
            write(path, records)
            prices = {'long_context_threshold': 272000, 'fallback_model': 'gpt-5.6-sol',
                      'models': {'gpt-5.6-sol': {'short': {'input': 4, 'cached': .4, 'output': 20}}}}
            windows = runs.capacity({'a': str(home)}, prices)['a']
            self.assertEqual(len(windows), 2)
            self.assertEqual(windows[0]['by_model_effort'][0]['per_1_percent']['input'], 2)
            self.assertTrue(windows[0]['partial'])
            self.assertFalse(windows[1]['partial'])

    def test_capacity_uses_window_minutes_when_primary_is_weekly(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / 'sessions' / '2026' / '01' / '01' / 'rollout-one.jsonl'
            write(path, [row('2026-01-01T00:00:00Z', 'event_msg',
                             {'type': 'token_count', 'rate_limits': {'primary': {
                                 'used_percent': 0, 'resets_at': 1000,
                                 'window_minutes': 10080}}})])
            prices = {'long_context_threshold': 272000, 'fallback_model': 'x',
                      'models': {'x': {'short': {'input': 1, 'cached': 1, 'output': 1}}}}
            windows = runs.capacity({'a': str(home)}, prices)['a']
            self.assertEqual([window['kind'] for window in windows], ['weekly'])

    def test_capacity_boundary_record_belongs_only_to_next_group(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / 'sessions' / '2026' / '01' / '01' / 'rollout-one.jsonl'
            records = [row('2026-01-01T00:00:00Z', 'turn_context', {'model': 'x'})]
            for time, pct, reset in [('00:00:00', 0, 1000), ('00:00:02', 50, 1000),
                                     ('00:00:02', 0, 2000), ('00:00:04', 100, 2000)]:
                records.append(row('2026-01-01T' + time + 'Z', 'event_msg',
                    {'type': 'token_count', 'rate_limits': {'primary': {
                        'used_percent': pct, 'resets_at': reset}}}))
            records.append(row('2026-01-01T00:00:02Z', 'token_usage_record',
                {'usage': {'input_tokens': 10, 'output_tokens': 1}}))
            write(path, records)
            prices = {'long_context_threshold': 272000, 'fallback_model': 'x',
                      'models': {'x': {'short': {'input': 1, 'cached': 1, 'output': 1}}}}
            windows = runs.capacity({'a': str(home)}, prices)['a']
            self.assertEqual([sum(group['samples'] for group in window['by_model_effort'])
                              for window in windows], [0, 1])


if __name__ == '__main__':
    unittest.main()
