from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('mode', default_value='sim', choices=['sim','hardware']),
        DeclareLaunchArgument('calib_dir', default_value='~/.ros/dual_arm_calib/sim'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('mount_revision', default_value=''),
        DeclareLaunchArgument('pose_signature', default_value=''),
        Node(package='dual_arm_vision_adapter', executable='calibration_status', parameters=[{
            'mode':LaunchConfiguration('mode'), 'calib_dir':LaunchConfiguration('calib_dir'),
            'mount_revision':LaunchConfiguration('mount_revision'), 'pose_signature':LaunchConfiguration('pose_signature'),
            'use_sim_time':LaunchConfiguration('use_sim_time')}], output='screen')])
