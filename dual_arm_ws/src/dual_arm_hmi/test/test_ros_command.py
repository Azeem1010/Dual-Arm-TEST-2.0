# Imports stay inside the tests: importing rclpy at collection would break test_fake_source's no-ROS check.
TORQUE = '/controller_manager/set_hardware_component_state'


def test_torque_request_activates_the_hardware_component():
    from controller_manager_msgs.srv import SetHardwareComponentState
    from dual_arm_hmi.sources.ros_command import HARDWARE_COMPONENT, SERVICES, request_for
    request = request_for(TORQUE)
    assert SERVICES[TORQUE][0] is SetHardwareComponentState
    assert request.name == HARDWARE_COMPONENT == 'DualArmSystem'
    assert request.target_state.id == 3 and request.target_state.label == 'active'


def test_torque_reply_uses_ok():
    from controller_manager_msgs.srv import SetHardwareComponentState
    from dual_arm_hmi.sources.ros_command import reply_from
    reply = reply_from(TORQUE, SetHardwareComponentState.Response(ok=True))
    assert reply.ok and reply.service == TORQUE


def test_switch_controller_activates_both_arms_strictly():
    from controller_manager_msgs.srv import SwitchController
    from dual_arm_hmi.sources.ros_command import reply_from, request_for
    request = request_for('/controller_manager/switch_controller')
    assert list(request.activate_controllers) == ['arm1_controller', 'arm2_controller']
    assert request.strictness == SwitchController.Request.STRICT
    assert reply_from('/controller_manager/switch_controller', SwitchController.Response(ok=True)).ok
    assert not reply_from('/controller_manager/switch_controller', SwitchController.Response(ok=False)).ok


def test_suction_off_publishes_zero_and_needs_the_zero_echo():
    from std_msgs.msg import Int32
    from dual_arm_hmi.sources.ros_command import SERVICES, SUCTION_OFF, reply_from, request_for
    assert SERVICES[SUCTION_OFF][0] is Int32 and request_for(SUCTION_OFF).data == 0
    assert reply_from(SUCTION_OFF, 0).ok
    assert not reply_from(SUCTION_OFF, 3).ok
