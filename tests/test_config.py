import unittest
from unittest.mock import patch
import os
import sys

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config

class TestConfigModule(unittest.TestCase):


    @patch('config.glob.glob')
    @patch('config.os.path.getmtime')
    def test_find_latest_feedback_file(self, mock_getmtime, mock_glob):
        """Test finding the latest feedback file with mocking."""
        # Scenario 1: No files found
        mock_glob.return_value = []
        result = config.find_latest_feedback_file()
        self.assertEqual(result, os.path.join(config.BASE_DIR, "quality_feedback_report_28SEP2026_142900.csv"))

        # Scenario 2: Multiple files found
        def glob_side_effect(pattern):
            if "quality_feedback_report_*.csv" in pattern:
                return [
                    os.path.join(config.BASE_DIR, "quality_feedback_report_1.csv"),
                    os.path.join(config.BASE_DIR, "quality_feedback_report_2.csv")
                ]
            elif "*feedback*.csv" in pattern:
                return [
                    os.path.join(config.BASE_DIR, "other_feedback_1.csv")
                ]
            return []

        mock_glob.side_effect = glob_side_effect

        def getmtime_side_effect(filename):
            times = {
                os.path.join(config.BASE_DIR, "quality_feedback_report_1.csv"): 100,
                os.path.join(config.BASE_DIR, "quality_feedback_report_2.csv"): 300,
                os.path.join(config.BASE_DIR, "other_feedback_1.csv"): 200,
            }
            return times.get(filename, 0)

        mock_getmtime.side_effect = getmtime_side_effect

        result = config.find_latest_feedback_file()
        self.assertEqual(result, os.path.join(config.BASE_DIR, "quality_feedback_report_2.csv"))

    def test_gas_charge_rates_and_labels(self):
        """Test capacity-aware gas calculation across all appliance categories."""
        # Split ACs
        charge, label = config.calculate_gas_charge("GS-12PITH11W")
        self.assertEqual(charge, 5500)
        self.assertIn("1.0 Ton", label)

        charge, label = config.calculate_gas_charge("GS-18PITH11W")
        self.assertEqual(charge, 7000)
        self.assertIn("1.5 Ton", label)

        charge, label = config.calculate_gas_charge("GS-24PITH11W")
        self.assertEqual(charge, 8500)
        self.assertIn("2.0 Ton", label)

        charge, label = config.calculate_gas_charge("GF-36TFIH")
        self.assertEqual(charge, 13000)
        self.assertIn("3.0 Ton", label)

        charge, label = config.calculate_gas_charge("GKH48K3FI")
        self.assertEqual(charge, 13000)
        self.assertIn("4.0 Ton", label)

        # Refrigerators
        charge, label = config.calculate_gas_charge("GR-E8890G-CB3")
        self.assertEqual(charge, 4000)
        self.assertIn("Refrigerator", label)

        # Water Dispensers
        charge, label = config.calculate_gas_charge("WD-300F")
        self.assertEqual(charge, 3500)
        self.assertIn("Water Dispenser", label)

        charge, label = config.calculate_gas_charge("GW-JL500FC")
        self.assertEqual(charge, 3500)
        self.assertIn("Water Dispenser", label)

        # None / Empty input fallback
        charge, label = config.calculate_gas_charge("")
        self.assertEqual(charge, 5500)
        self.assertIn("Standard", label)

    def test_tokenize_appliance_model(self):
        """Test brand, category, tonnage, and series tokenization."""
        tok = config.tokenize_appliance_model("GS-18PITH11W")
        self.assertEqual(tok['brand'], "Gree")
        self.assertEqual(tok['category'], "Split AC")
        self.assertEqual(tok['tonnage'], "1.5 Ton")
        self.assertEqual(tok['series'], "PITH")

        tok_ref = config.tokenize_appliance_model("GR-E8890G")
        self.assertEqual(tok_ref['brand'], "Gree")
        self.assertEqual(tok_ref['category'], "Refrigerator")

        tok_eco = config.tokenize_appliance_model("ES-12DU01WG")
        self.assertEqual(tok_eco['brand'], "EcoStar")
        self.assertEqual(tok_eco['category'], "Split AC")
        self.assertEqual(tok_eco['tonnage'], "1.0 Ton")

        tok_floor = config.tokenize_appliance_model("GF-48TFIH")
        self.assertEqual(tok_floor['category'], "Floor Standing AC")
        self.assertEqual(tok_floor['tonnage'], "4.0 Ton")

    def test_classify_component_role(self):
        """Test classification of spare parts into component roles."""
        self.assertEqual(config.classify_component_role("Evaporator Assy 18PITH"), "Evaporator Assembly")
        self.assertEqual(config.classify_component_role("PCB ODU Inverter Board"), "Outdoor Inverter PCB")
        self.assertEqual(config.classify_component_role("PCB IDU Display"), "Indoor Main PCB")
        self.assertEqual(config.classify_component_role("Compressor QD36LW"), "Compressor & Fittings")
        self.assertEqual(config.classify_component_role("Cut-off Valve 1/4 inch"), "Cut-Off Valve (1/4\")")
        self.assertEqual(config.classify_component_role("3/8 Valve 71302395"), "Cut-Off Valve (3/8\")")
        self.assertEqual(config.classify_component_role("5/8 Cut-off valve"), "Cut-Off Valve (5/8\")")
        self.assertEqual(config.classify_component_role("Packing Carton Box"), "Component Hardware")

    def test_valve_tonnage_compatibility(self):
        """Test physical line pairing and tonnage compatibility rules for cut-off valves."""
        # 1.0 Ton: strictly 1/4" + 3/8". Rejects 1/2" and 5/8"
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (1/4\")", "Valve 1/4", "1.0 Ton"))
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (3/8\")", "Valve 3/8", "1.0 Ton"))
        self.assertFalse(config.is_valve_tonnage_compatible("Cut-Off Valve (1/2\")", "Valve 1/2", "1.0 Ton"))
        self.assertFalse(config.is_valve_tonnage_compatible("Cut-Off Valve (5/8\")", "Valve 5/8", "1.0 Ton"))

        # 1.5 Ton: strictly 1/4" + 1/2". Rejects 3/8" and 5/8"
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (1/4\")", "Valve 1/4", "1.5 Ton"))
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (1/2\")", "Valve 1/2", "1.5 Ton"))
        self.assertFalse(config.is_valve_tonnage_compatible("Cut-Off Valve (3/8\")", "Valve 3/8", "1.5 Ton"))
        self.assertFalse(config.is_valve_tonnage_compatible("Cut-Off Valve (5/8\")", "Valve 5/8", "1.5 Ton"))

        # 2.0 Ton / 3.0 Ton: strictly 1/4" + 5/8". Rejects 3/8" and 1/2"
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (1/4\")", "Valve 1/4", "2.0 Ton"))
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (5/8\")", "Valve 5/8", "2.0 Ton"))
        self.assertFalse(config.is_valve_tonnage_compatible("Cut-Off Valve (1/2\")", "Valve 1/2", "2.0 Ton"))

        # 4.0 Ton / 5.0 Ton: strictly 3/8" + 5/8". Rejects 1/4" and 1/2"
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (3/8\")", "Valve 3/8", "4.0 Ton"))
        self.assertTrue(config.is_valve_tonnage_compatible("Cut-Off Valve (5/8\")", "Valve 5/8", "4.0 Ton"))
        self.assertFalse(config.is_valve_tonnage_compatible("Cut-Off Valve (1/4\")", "Valve 1/4", "4.0 Ton"))

    def test_tonnage_valve_pairing(self):
        """Test tonnage valve pairing standards across AC capacities."""
        suction_15, liquid_15 = config.get_tonnage_valve_pairing("1.5 Ton")
        self.assertEqual(suction_15, "Cut-Off Valve (1/2\")")
        self.assertEqual(liquid_15, "Cut-Off Valve (1/4\")")

        suction_10, liquid_10 = config.get_tonnage_valve_pairing("1.0 Ton")
        self.assertEqual(suction_10, "Cut-Off Valve (3/8\")")
        self.assertEqual(liquid_10, "Cut-Off Valve (1/4\")")

if __name__ == "__main__":
    unittest.main()
