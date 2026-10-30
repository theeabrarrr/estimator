import unittest
import os
import sys
import urllib.parse
from unittest.mock import patch
import app

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config

class TestAppLogic(unittest.TestCase):

    def test_quotation_math_and_formatting(self):
        """Verify estimate calculation logic and WhatsApp quotation string building."""
        selected_model = "GS-18PITH11W"
        selected_parts = [
            {'part_no': '11001060868', 'description': 'Evaporator Assy', 'price': 26000},
            {'part_no': '7130239', 'description': 'Cut-off Valve', 'price': 1600}
        ]

        parts_total = sum(p['price'] for p in selected_parts)
        self.assertEqual(parts_total, 27600)

        visit_charges = config.VISIT_CHARGES
        mobility_charges = config.MOBILITY_CHARGES
        gas_amount, gas_label = config.calculate_gas_charge(selected_model)

        grand_total = parts_total + visit_charges + mobility_charges + gas_amount
        self.assertEqual(grand_total, 27600 + 600 + 2000 + 7000)

        # WhatsApp URL encoding test
        quote_text = f"Model: {selected_model}\nTotal: Rs. {grand_total:,}"
        encoded = urllib.parse.quote(quote_text)
        self.assertIn("GS-18PITH11W", encoded)


    @patch('app.get_all_models_for_estimator')
    def test_get_cached_all_models(self, mock_get_all_models):
        """Verify get_cached_all_models correctly wraps get_all_models_for_estimator."""
        mock_get_all_models.return_value = ["ModelA", "ModelB"]
        app.get_cached_all_models.clear()

        result = app.get_cached_all_models()

        mock_get_all_models.assert_called_once()
        self.assertEqual(result, ["ModelA", "ModelB"])

if __name__ == "__main__":
    unittest.main()
