import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BillingSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = json.loads((ROOT / 'prices.json').read_text())
        cls.subscription = json.loads((ROOT / 'prices.subscription.json').read_text())

    def test_standard_credits_map_to_current_api_reference_rates(self):
        references = self.subscription['_api_reference_prices']
        for model, spec in self.subscription['models'].items():
            api = references.get(model)
            standard = spec['standard']
            if not api:
                continue
            for field in ('input', 'cached', 'output'):
                if field not in api:
                    continue
                ratio = standard[field] / api[field]
                expected = 25
                # The subscription page rounds a few displayed credit rates (notably
                # gpt-5.4-mini output), so allow a small published-table tolerance.
                self.assertAlmostEqual(ratio, expected, delta=0.2,
                                       msg=f'{model} {field}')

    def test_sol_current_promotion_is_the_explicit_reference(self):
        current = self.api['models']['gpt-5.6-sol']['short']
        original = self.subscription['_api_reference_prices']['gpt-5.6-sol']
        self.assertEqual((current['input'], current['output']), (4.0, 20.0))
        self.assertEqual((original['input'], original['output']), (4, 20))
        self.assertEqual(self.subscription['_api_equivalent_basis'], 'current_api_standard_price')

    def test_fast_multipliers_are_model_specific(self):
        self.assertEqual(self.subscription['models']['gpt-5.6-sol']['fast_multiplier'], 2.5)
        self.assertEqual(self.subscription['models']['gpt-6-astra']['fast_multiplier'], 2.5)
        self.assertEqual(self.subscription['models']['gpt-5.4']['fast_multiplier'], 2.0)


if __name__ == '__main__':
    unittest.main()
