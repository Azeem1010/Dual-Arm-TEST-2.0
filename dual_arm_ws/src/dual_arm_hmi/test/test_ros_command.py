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
