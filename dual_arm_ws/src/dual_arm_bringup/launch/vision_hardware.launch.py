"""Hardware vision: the environment camera decides, the arm cameras only monitor, one at a time.

Starts the environment camera (vision_pkg, no vision nodes), env_scene_node, the
env_scene bridge for the operator display, and the arm camera switch, which
starts and stops the two arm cameras so that at most one streams (they share a
USB 2.0 hub that cannot carry both). Nothing here starts an arm camera directly.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    arg = LaunchConfiguration
    env_camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare('vision_pkg'), 'launch', 'vision.launch.py'])),
        launch_arguments={'arm_camera': 'none', 'env_camera': 'true', 'vision_nodes': 'false', 'show_debug': 'false',
                          'env_cam_device': arg('env_cam_device'), 'calib_dir': arg('calib_dir')}.items())
    return LaunchDescription([
        DeclareLaunchArgument('env_cam_device', default_value='',
                              description='環境相機裝置路徑；空 = vision_pkg 的 config/cameras.yaml'),
        DeclareLaunchArgument('arm1_cam_device', default_value='', description='手臂 1 鏡頭裝置路徑；空 = cameras.yaml'),
        DeclareLaunchArgument('arm2_cam_device', default_value='', description='手臂 2 鏡頭裝置路徑；空 = cameras.yaml'),
        DeclareLaunchArgument('calib_dir', default_value='', description='vision_pkg 校正檔目錄（空 = 預設）'),
        env_camera,
        Node(package='env_scene', executable='env_scene_node', name='env_scene_node', output='screen',
             parameters=[PathJoinSubstitution([FindPackageShare('env_scene'), 'config', 'env_scene.yaml']),
                         {'show_debug': False}]),
        Node(package='dual_arm_vision_adapter', executable='env_scene_bridge', output='screen'),
        Node(package='dual_arm_vision_adapter', executable='arm_camera_switch', output='screen',
             parameters=[{'arm1_cam_device': arg('arm1_cam_device'), 'arm2_cam_device': arg('arm2_cam_device')}]),
    ])
