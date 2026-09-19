import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BillingSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = json.loads((ROOT / 'prices.json').read_text())
        cls.subscription = json.loads((ROOT / 'prices.subscription.json').read_text())

    def test_published_standard_credits_map_to_api_standard_rates(self):
        ratio = self.subscription['_credits_per_api_usd']
        for model, spec in self.subscription['models'].items():
            api = self.api['models'].get(model, {}).get('short')
            standard = spec['standard']
            if not api:
                continue
            for field in ('input', 'cached', 'output'):
                if field not in api:
                    continue
                # The subscription page rounds a few displayed credit rates (notably
                # gpt-5.4-mini output), so allow a small published-table tolerance.
                self.assertAlmostEqual(standard[field] / ratio, api[field], delta=0.05,
                                       msg=f'{model} {field}')

    def test_fast_multipliers_are_model_specific(self):
        self.assertEqual(self.subscription['models']['gpt-5.6-sol']['fast_multiplier'], 2.5)
        self.assertEqual(self.subscription['models']['gpt-6-astra']['fast_multiplier'], 2.5)
        self.assertEqual(self.subscription['models']['gpt-5.4']['fast_multiplier'], 2.0)


if __name__ == '__main__':
    unittest.main()
