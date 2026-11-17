import importlib.util
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
spec = importlib.util.spec_from_file_location('proto', '/home/orin/projects/dual_arm_system/dual_arm_ws/src/dual_arm_bringup/launch/hardware_prototype.launch.py')
proto = importlib.util.module_from_spec(spec); spec.loader.exec_module(proto)
def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument('esp32_port', default_value=''),
        DeclareLaunchArgument('microros_setup', default_value='~/microros_ws/install/local_setup.bash'),
        OpaqueFunction(function=proto.micro_ros_agent)])
