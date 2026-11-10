import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import yaml

from dual_arm_coordinator.tools.axis_circle import COUNTS_PER_RADIAN, SheetError, analyse, fit_circle, main


def sheet(centre=(-10.0, 0.0), radius=60.0, yaws_deg=(-60, -30, 0, 30, 60), direction=1, zero=196.0,
          noise_mm=0.0, raw=True, seed=1):
    rng = np.random.default_rng(seed)
    points = []
    for yaw in np.radians(yaws_deg):
        f = centre[0] + radius * math.cos(yaw) + rng.normal(0.0, noise_mm) if noise_mm else centre[0] + radius * math.cos(yaw)
        l = centre[1] + radius * math.sin(yaw) + rng.normal(0.0, noise_mm) if noise_mm else centre[1] + radius * math.sin(yaw)
        point = {'f': float(f), 'l': float(l)}
        if raw:
            point['raw'] = float(zero + direction * yaw * COUNTS_PER_RADIAN)
        points.append(point)
    return {'unit': 'mm', 'points': points}


class Circle(unittest.TestCase):
    def test_exact_points_recover_axis_and_direction(self):
        report = analyse(sheet())
        self.assertAlmostEqual(report['axis_f'], -10.0, places=6)
        self.assertAlmostEqual(report['axis_l'], 0.0, places=6)
        self.assertAlmostEqual(report['radius'], 60.0, places=6)
        self.assertEqual(report['j1_direction'], 1)
        self.assertAlmostEqual(report['raw_facing_field'], 196.0, places=6)
        self.assertLess(report['raw_residual_max_counts'], 1e-6)
        self.assertAlmostEqual(report['angular_span_deg'], 120.0, places=6)

    def test_negative_direction_is_detected(self):
        report = analyse(sheet(direction=-1, zero=512.0))
        self.assertEqual(report['j1_direction'], -1)
        self.assertAlmostEqual(report['raw_facing_field'], 512.0, places=6)

    def test_ruler_noise_gives_bounded_error_and_estimate(self):
        report = analyse(sheet(noise_mm=1.0, yaws_deg=(-80, -50, -20, 10, 40, 70), seed=4))
        self.assertLess(math.hypot(report['axis_f'] + 10.0, report['axis_l']), 3.0)
        self.assertIsNotNone(report['axis_standard_error'])
        self.assertTrue(all(0.0 < value < 3.0 for value in report['axis_standard_error']))
        self.assertGreater(report['radial_residual_rms'], 0.0)
        self.assertEqual(report['j1_direction'], 1)
        self.assertLess(abs(report['raw_facing_field'] - 196.0), 20.0)

    def test_points_behind_the_base_do_not_break_the_raw_fit(self):
        report = analyse(sheet(yaws_deg=(150, 170, -170, -150), zero=300.0))
        self.assertEqual(report['j1_direction'], 1)
        self.assertLess(report['raw_residual_max_counts'], 1e-6)
        self.assertAlmostEqual(report['angular_span_deg'], 60.0, places=6)

    def test_three_points_fit_without_error_estimate(self):
        report = analyse(sheet(yaws_deg=(-40, 0, 40)))
        self.assertIsNone(report['axis_standard_error'])

    def test_without_raw_no_direction_is_reported(self):
        report = analyse(sheet(raw=False))
        self.assertNotIn('j1_direction', report)


class Refused(unittest.TestCase):
    def test_too_few_points(self):
        with self.assertRaises(SheetError):
            analyse(sheet(yaws_deg=(0, 30)))

    def test_collinear_points(self):
        with self.assertRaises(SheetError):
            fit_circle([(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)])

    def test_nearly_collinear_points(self):
        with self.assertRaises(SheetError):
            fit_circle([(0.0, 0.0), (10.0, 1e-9), (20.0, 0.0)])

    def test_missing_or_bad_values(self):
        doc = sheet()
        doc['points'][1]['l'] = None
        with self.assertRaises(SheetError):
            analyse(doc)
        doc = sheet()
        doc['points'][0]['f'] = float('nan')
        with self.assertRaises(SheetError):
            analyse(doc)

    def test_raw_on_some_points_only(self):
        doc = sheet()
        del doc['points'][2]['raw']
        with self.assertRaises(SheetError):
            analyse(doc)

    def test_unit_is_required(self):
        doc = sheet()
        del doc['unit']
        with self.assertRaises(SheetError):
            analyse(doc)


class Command(unittest.TestCase):
    def test_writes_report_and_refuses_bad_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad, out = Path(tmp, 'good.yaml'), Path(tmp, 'bad.yaml'), Path(tmp, 'report.json')
            good.write_text(yaml.safe_dump(sheet()), encoding='utf-8')
            bad.write_text(yaml.safe_dump({'unit': 'mm', 'points': []}), encoding='utf-8')
            self.assertEqual(main([str(good), str(out)]), 0)
            self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['status'], 'PASS')
            self.assertEqual(main([str(bad)]), 1)
            self.assertEqual(main([]), 2)


if __name__ == '__main__':
    unittest.main()
