"""PROTOTYPE: run the whole task on the real arms with estimated settings.

User decision 2026-11-13: the flow must run end to end (detect, plan, pick in A,
hand over in B, place in C); accuracy and suction success are not required.
Starts hardware.launch.py with the prototype calibration and controllers, no
e-stop heartbeat requirement, the hardware vision and the coordinator with the
prototype config. None of this is calibration evidence.

The CM-530 power switch is the only emergency stop: one person keeps a hand on
it. Start the ESP32 micro-ROS agent separately (ORIN_DEPLOYMENT 6.1). Then:
torque on, /safety/reset, start the task.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    arg = LaunchConfiguration
    bringup = FindPackageShare('dual_arm_bringup')
    hardware = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([bringup, 'launch', 'hardware.launch.py'])),
        launch_arguments={
            'port': arg('port'), 'use_mock_serial': arg('use_mock_serial'), 'calibration_file': arg('calibration_file'),
            'enable_motion': 'true', 'require_estop': 'false',
            'controllers_file': PathJoinSubstitution([FindPackageShare('dual_arm_controllers'), 'config',
                                                      'controllers_prototype.yaml']),
        }.items())
    vision = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([bringup, 'launch', 'vision_hardware.launch.py'])),
        launch_arguments={name: arg(name) for name in
                          ('env_cam_device', 'arm1_cam_device', 'arm2_cam_device', 'calib_dir')}.items())
    coordinator = Node(
        package='dual_arm_coordinator', executable='coordinator_node', output='screen',
        parameters=[{
            'config_path': PathJoinSubstitution([FindPackageShare('dual_arm_coordinator'), 'config', 'prototype',
                                                 'coordinator.yaml']),
            'calibration_path': arg('calibration_file'),
            'observation_source': 'env_scene',
            'require_safety': True,
            'cycles': ParameterValue(arg('cycles'), value_type=int),
            'journal_path': ParameterValue(arg('journal_path'), value_type=str),
        }])
    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0', description='CM-530 序列埠'),
        DeclareLaunchArgument('calibration_file',
                              default_value=PathJoinSubstitution([FindPackageShare('cm530_hardware'), 'config',
                                                                  'calibration_prototype.yaml']),
                              description='馬達校正檔；預設是 prototype 估計值'),
        DeclareLaunchArgument('use_mock_serial', default_value='false',
                              description='測試用 Mock Serial（要搭配 mock 校正檔）'),
        DeclareLaunchArgument('env_cam_device', default_value='', description='環境相機裝置；空 = cameras.yaml'),
        DeclareLaunchArgument('arm1_cam_device', default_value='', description='手臂 1 鏡頭裝置；空 = cameras.yaml'),
        DeclareLaunchArgument('arm2_cam_device', default_value='', description='手臂 2 鏡頭裝置；空 = cameras.yaml'),
        DeclareLaunchArgument('calib_dir', default_value='', description='vision_pkg 校正檔目錄（空 = 預設）'),
        DeclareLaunchArgument('cycles', default_value='1', description='搬運幾件（1～8）'),
        DeclareLaunchArgument('journal_path', default_value='', description='任務紀錄檔；空 = 設定檔的路徑'),
        LogInfo(msg='PROTOTYPE：估計校正、沒有急停心跳、吸盤自動確認；CM-530 電源開關是唯一急停'),
        hardware, vision, coordinator,
    ])
