"""MotionGateway._require_valid_all: every waypoint is checked, the requests go out together (2026-11-17)."""
import unittest

from dual_arm_coordinator.gateways import motion
from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.workflow.ports import TaskFault

PATH = [[0.0, 0.5, 0.5, 0.0], [0.0, 0.52, 0.48, 0.0], [0.0, 0.54, 0.46, 0.0], [0.0, 0.56, 0.44, 0.0]]


class Future:
    def __init__(self, client, response):
        self.client, self.response = client, response

    def done(self):
        self.client.events.append('wait')
        if self in self.client.dropped:
            return False
        self.client.answered(self)
        return True

    def result(self):
        return self.response


class Response:
    def __init__(self, valid, contacts=()):
        self.valid, self.contacts = valid, list(contacts)


class Contact:
    contact_body_1, contact_body_2 = 'arm1_link_4', 'cap_in_b'


class Client:
    """A service whose request queue holds QUEUE requests, as move_group's default QoS (depth 10).

    A request sent while QUEUE others wait unanswered is dropped and never answered (Mock Serial
    run 2026-11-18: a 100-point path timed out after 20 s).
    """
    QUEUE = 10

    def __init__(self, invalid=()):
        self.invalid, self.events, self.requests, self.available = set(invalid), [], [], True
        self.pending, self.dropped, self.most_pending = [], set(), 0

    def wait_for_service(self, timeout_sec):
        self.events.append('service')
        return self.available

    def call_async(self, request):
        index = len(self.requests)
        self.requests.append(request)
        self.events.append('send')
        valid = index not in self.invalid
        future = Future(self, Response(valid, () if valid else (Contact(),)))
        if len(self.pending) >= self.QUEUE:
            self.dropped.add(future)
        else:
            self.pending.append(future)
            self.most_pending = max(self.most_pending, len(self.pending))
        return future

    def answered(self, future):
        if future in self.pending:
            self.pending.remove(future)


class ValidAll(unittest.TestCase):
    def make(self, client):
        gateway = MotionGateway.__new__(MotionGateway)
        gateway._validity = client
        gateway._cfg = {'goal_submit_s': 5.0}
        gateway._guard = lambda: None
        gateway._arms = {'arm1': {'planning_group': 'arm1'}}
        model = type('Model', (), {'names': ['j1', 'j2', 'j3', 'j4']})()
        gateway._models = {'arm1': model}
        return gateway

    def test_every_waypoint_is_checked(self):
        client = Client()
        self.make(client)._require_valid_all('arm1', PATH, 'arm1 lift')
        self.assertEqual([list(r.robot_state.joint_state.position) for r in client.requests], PATH)
        self.assertEqual(client.requests[0].group_name, 'arm1')

    def test_requests_go_out_before_any_answer_is_awaited(self):
        client = Client()
        self.make(client)._require_valid_all('arm1', PATH, 'arm1 lift')
        self.assertEqual(client.events.count('service'), 1)
        self.assertEqual(client.events[:1 + len(PATH)], ['service'] + ['send'] * len(PATH))

    def test_a_long_path_never_overflows_the_service_queue(self):
        # A fixed transit HOME -> above B is about 130 joint-line points.
        long_path = [[0.0, 0.5 + 0.01 * i, 0.5, 0.0] for i in range(130)]
        client = Client()
        self.make(client)._require_valid_all('arm1', long_path, 'arm1 home fixed path')
        self.assertEqual(len(client.requests), 130)
        self.assertEqual(client.dropped, set())
        self.assertLessEqual(client.most_pending, motion._VALIDITY_IN_FLIGHT)
        self.assertLess(motion._VALIDITY_IN_FLIGHT, Client.QUEUE)

    def test_an_invalid_waypoint_late_in_a_long_path_still_faults(self):
        long_path = [[0.0, 0.5 + 0.01 * i, 0.5, 0.0] for i in range(40)]
        client = Client(invalid={33})
        with self.assertRaises(TaskFault):
            self.make(client)._require_valid_all('arm1', long_path, 'arm1 home fixed path')

    def test_an_invalid_waypoint_faults_with_its_contacts(self):
        client = Client(invalid={2})
        with self.assertRaises(TaskFault) as caught:
            self.make(client)._require_valid_all('arm1', PATH, 'arm1 lift')
        self.assertIn('arm1 lift: state is invalid', str(caught.exception))
        self.assertIn('arm1_link_4/cap_in_b', str(caught.exception))

    def test_unavailable_service_faults(self):
        client = Client()
        client.available = False
        with self.assertRaises(TaskFault) as caught:
            self.make(client)._require_valid_all('arm1', PATH, 'arm1 lift')
        self.assertIn('service is unavailable', str(caught.exception))

    def test_no_waypoints_calls_nothing(self):
        client = Client()
        self.make(client)._require_valid_all('arm1', [], 'arm1 lift')
        self.assertEqual(client.events, [])


if __name__ == '__main__':
    unittest.main()
