from types import SimpleNamespace as Reply
import unittest

from dual_arm_vision_adapter.env_scene_bridge import ScenePoller, at_home_from_status, env_calibration, to_zone_fields

BOTH_HOME = {'arm1': True, 'arm2': True}


def response(success=True, message='', **changes):
    scene = dict(valid=True, message='', coords_source='standard', arm1_valid=True, arm2_valid=True,
                 c_slots_valid=True, a_objects=[object(), object()], b_objects=[object()], c_occupied_count=3)
    scene.update(changes)
    if 'scene_message' in scene:
        scene['message'] = scene.pop('scene_message')
    return Reply(success=success, message=message, scene=Reply(**scene))


class ZoneFields(unittest.TestCase):
    def test_zone_fields_valid_scene(self):
        self.assertEqual(to_zone_fields(response(), BOTH_HOME),
                         dict(valid=True, message='', a_has_object=True, b_has_object=True, b_arm_clear=True,
                              c_object_count=3))

    def test_zone_fields_b_clear_needs_both_home(self):
        for at_home in ({'arm1': True, 'arm2': False}, {'arm1': True, 'arm2': None}, {}, None):
            with self.subTest(at_home):
                self.assertFalse(to_zone_fields(response(), at_home)['b_arm_clear'])

    def test_zone_fields_invalid_when_estimated(self):
        fields = to_zone_fields(response(coords_source='estimated'), BOTH_HOME)
        self.assertFalse(fields['valid'])
        self.assertIn('estimated', fields['message'])

    def test_zone_fields_invalid_on_failure(self):
        fields = to_zone_fields(response(success=False, message='no image'), BOTH_HOME)
        self.assertEqual((fields['valid'], fields['message']), (False, 'no image'))
        self.assertFalse(to_zone_fields(response(c_slots_valid=False), BOTH_HOME)['valid'])


class Calibration(unittest.TestCase):
    def test_calibration_passes_for_a_valid_scene(self):
        self.assertEqual(env_calibration(response()), (True, []))

    def test_calibration_reasons(self):
        for change, word in ((dict(coords_source='estimated'), 'estimated'), (dict(arm1_valid=False), 'arm1_valid'),
                             (dict(c_slots_valid=False), 'c_slots_valid'), (dict(valid=False, scene_message='no field'),
                                                                            'no field')):
            with self.subTest(word):
                passed, reasons = env_calibration(response(**change))
                self.assertFalse(passed)
                self.assertTrue(any(word in reason for reason in reasons), reasons)
        passed, reasons = env_calibration(response(success=False, message='timeout'))
        self.assertEqual((passed, reasons), (False, ['timeout']))


class Future:
    def __init__(self):
        self.value, self.finished = None, False

    def done(self):
        return self.finished

    def result(self):
        return self.value


class Polling(unittest.TestCase):
    def setUp(self):
        self.now, self.futures = 0.0, []
        self.poller = ScenePoller(self.call, lambda: self.now, timeout_s=2.0)

    def call(self):
        self.futures.append(Future())
        return self.futures[-1]

    def test_returns_each_finished_response_once(self):
        self.assertIsNone(self.poller.tick())
        self.futures[0].value, self.futures[0].finished = 'scene', True
        self.assertEqual(self.poller.tick(), 'scene')
        self.assertEqual(len(self.futures), 2)

    def test_abandons_a_request_that_never_returns(self):
        self.poller.tick()
        self.now = 1.0
        self.poller.tick()
        self.assertEqual(len(self.futures), 1)
        self.now = 2.5
        self.poller.tick()
        self.assertEqual(len(self.futures), 2)


class StatusParsing(unittest.TestCase):
    def test_at_home_from_status(self):
        self.assertEqual(at_home_from_status('{"at_home": {"arm1": true, "arm2": null}}'), {'arm1': True, 'arm2': None})
        self.assertIsNone(at_home_from_status('[]'))
        self.assertIsNone(at_home_from_status('oops'))


if __name__ == '__main__':
    unittest.main()
