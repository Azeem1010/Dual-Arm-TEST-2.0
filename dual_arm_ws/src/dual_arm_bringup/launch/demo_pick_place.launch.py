"""Simulated A-to-B-to-C task: the Gazebo workstation plus the coordinator node.

Objects are located from Gazebo ground truth, not from cameras. Start a run with
`ros2 service call /dual_arm/start std_srvs/srv/Trigger '{}'`.
"""
from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('gz_args', default_value='-r -s'),
        DeclareLaunchArgument('cycles', default_value='1'),
        # Slot 1 is out of reach in the current layout; 2 starts the run at slot 3.
        DeclareLaunchArgument('prefilled_slots', default_value='2'),
        DeclareLaunchArgument('journal_path', default_value=''),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(share('dual_arm_bringup') + '/launch/sim.launch.py'),
                                 launch_arguments={'gz_args': LaunchConfiguration('gz_args')}.items()),
        Node(package='dual_arm_coordinator', executable='coordinator_node', output='screen', parameters=[{
            'cycles': ParameterValue(LaunchConfiguration('cycles'), value_type=int),
            'simulation_prefilled_slots': ParameterValue(LaunchConfiguration('prefilled_slots'), value_type=int),
            'journal_path': ParameterValue(LaunchConfiguration('journal_path'), value_type=str),
        }]),
    ])
