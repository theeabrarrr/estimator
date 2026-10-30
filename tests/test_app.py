import unittest
import os
import sys
import urllib.parse

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import app
import pandas as pd
from unittest.mock import patch
from datetime import date


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


    def setUp(self):
        app.get_cached_performance_data.clear()

    @patch('app.fetch_performance_data')
    def test_get_cached_performance_data_happy_path(self, mock_fetch):
        # Test Case 1: Happy path
        mock_fetch.return_value = pd.DataFrame([
            {'closed_date': '2023-10-15', 'branch_name': 'Karachi 2 HA'},
            {'closed_date': '2023-11-20', 'branch_name': 'Lahore'},
        ])
        df, min_avail, max_avail, months, branches = app.get_cached_performance_data()
        self.assertEqual(len(df), 2)
        self.assertEqual(min_avail, date(2023, 10, 15))
        self.assertEqual(max_avail, date(2023, 11, 20))
        self.assertEqual(months, ['2023-11', '2023-10'])
        self.assertEqual(branches, ['Karachi 2 HA', 'Lahore'])

    @patch('app.fetch_performance_data')
    def test_get_cached_performance_data_empty(self, mock_fetch):
        # Test Case 2: Empty DataFrame
        mock_fetch.return_value = pd.DataFrame()
        df, min_avail, max_avail, months, branches = app.get_cached_performance_data()
        self.assertTrue(df.empty)
        self.assertIsNone(min_avail)
        self.assertIsNone(max_avail)
        self.assertEqual(months, [])
        # In current implementation, if df is empty, the return is `pd.DataFrame(), None, None, [], []`
        # But wait, looking at app.py:92-93:
        # if df is None or df.empty:
        #     return pd.DataFrame(), None, None, [], []
        # Let's verify branches is []
        self.assertEqual(branches, [])

    @patch('app.fetch_performance_data')
    def test_get_cached_performance_data_none(self, mock_fetch):
        # Test Case 3: None
        mock_fetch.return_value = None
        df, min_avail, max_avail, months, branches = app.get_cached_performance_data()
        self.assertTrue(df.empty)
        self.assertIsNone(min_avail)
        self.assertIsNone(max_avail)
        self.assertEqual(months, [])
        self.assertEqual(branches, [])

    @patch('app.fetch_performance_data')
    def test_get_cached_performance_data_nulls(self, mock_fetch):
        # Test Case 4: Null dates and branch_name
        mock_fetch.return_value = pd.DataFrame([
            {'closed_date': 'invalid_date', 'branch_name': None},
            {'closed_date': '2023-10-15', 'branch_name': 'Karachi 2 HA'},
            {'closed_date': None, 'branch_name': 'Lahore'},
            {'closed_date': '2023-09-01', 'branch_name': ''},
        ])
        df, min_avail, max_avail, months, branches = app.get_cached_performance_data()
        self.assertEqual(min_avail, date(2023, 9, 1))
        self.assertEqual(max_avail, date(2023, 10, 15))
        self.assertEqual(months, ['2023-10', '2023-09'])
        self.assertEqual(branches, ['Karachi 2 HA', 'Lahore'])

if __name__ == "__main__":
    unittest.main()
