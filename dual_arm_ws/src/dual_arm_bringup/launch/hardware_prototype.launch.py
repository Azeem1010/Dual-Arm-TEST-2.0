"""PROTOTYPE: run the whole task on the real arms with estimated settings.

User decision 2026-11-13: the flow must run end to end (detect, plan, pick in A,
hand over in B, place in C); accuracy and suction success are not required.
Starts hardware.launch.py with the prototype calibration and controllers, no
e-stop heartbeat requirement, the hardware vision and the coordinator with the
prototype config. None of this is calibration evidence.

The CM-530 power switch is the only emergency stop: one person keeps a hand on
it. With esp32_port set, the ESP32 micro-ROS agent starts and stops with this
launch (ORIN_DEPLOYMENT 6.1). The board only finds the agent while it boots, so a
few seconds after the agent starts esp32_reset.py restarts it through RTS (= EN;
user request 2026-11-18); its relays start off. Then: torque on, /safety/reset,
start the task.
"""
import shlex
from pathlib import Path

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, LogInfo, OpaqueFunction,
                            TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackagePrefix, FindPackageShare


def micro_ros_agent(context):
    """The agent from its own workspace; it is not part of this colcon workspace."""
    port = LaunchConfiguration('esp32_port').perform(context).strip()
    if not port:
        return [LogInfo(msg='沒有設定 esp32_port：不啟動 micro-ROS agent，吸盤要另外接上')]
    setup = Path(LaunchConfiguration('microros_setup').perform(context)).expanduser()
    if not setup.is_file():
        raise RuntimeError(f'micro-ROS agent setup {setup} not found (ORIN_DEPLOYMENT 6.1)')
    command = (f'source {shlex.quote(str(setup))} && exec ros2 run micro_ros_agent micro_ros_agent '
               f'serial --dev {shlex.quote(port)} -b 115200')
    actions = [ExecuteProcess(cmd=['bash', '-c', command], name='micro_ros_agent', output='screen')]
    delay = float(LaunchConfiguration('esp32_reset_delay_s').perform(context))
    if delay > 0:
        # Pressing EN by hand after every start (2026-11-17/18) is replaced by an RTS pulse once the
        # agent has opened the port; the board connects about 2 s later.
        reset = str(Path(FindPackagePrefix('dual_arm_bringup').perform(context)) / 'lib' / 'dual_arm_bringup' / 'esp32_reset.py')
        actions.append(TimerAction(period=delay, actions=[
            ExecuteProcess(cmd=['python3', reset, port], name='esp32_reset', output='screen')]))
    return actions


def generate_launch_description():
    arg = LaunchConfiguration
    bringup = FindPackageShare('dual_arm_bringup')
    hardware = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([bringup, 'launch', 'hardware.launch.py'])),
        launch_arguments={
            'port': arg('port'), 'use_mock_serial': arg('use_mock_serial'), 'calibration_file': arg('calibration_file'),
            'enable_motion': 'true', 'require_estop': 'false',
            # 2026-11-17: a holding AX-12 hunts by up to 4 counts (0.02 rad) at rest, and a loaded joint
            # creeps between planning and execution; the 0.01 rad default aborted HOME moves.
            'moveit_start_tolerance': '0.03',
            'controllers_file': PathJoinSubstitution([FindPackageShare('dual_arm_controllers'), 'config',
                                                      'controllers_prototype.yaml']),
        }.items())
    vision = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([bringup, 'launch', 'vision_hardware.launch.py'])),
        launch_arguments={name: arg(name) for name in
                          ('env_cam_device', 'arm1_cam_device', 'arm2_cam_device', 'calib_dir', 'show_debug')}.items())
    coordinator = Node(
        package='dual_arm_coordinator', executable='coordinator_node', output='screen',
        parameters=[{
            'config_path': PathJoinSubstitution([FindPackageShare('dual_arm_coordinator'), 'config', 'prototype',
                                                 'coordinator.yaml']),
            'calibration_path': arg('home_calibration_file'),
            'observation_source': 'env_scene',
            'require_safety': False,   # no /safety/estop heartbeat in the prototype (D8 not built)
            'cycles': ParameterValue(arg('cycles'), value_type=int),
            'journal_path': ParameterValue(arg('journal_path'), value_type=str),
        }])
    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0', description='CM-530 序列埠'),
        DeclareLaunchArgument('calibration_file',
                              default_value=PathJoinSubstitution([FindPackageShare('cm530_hardware'), 'config',
                                                                  'calibration_prototype.yaml']),
                              description='馬達校正檔；預設是 prototype 估計值'),
        DeclareLaunchArgument('home_calibration_file', default_value=arg('calibration_file'),
                              description='coordinator 算 HOME 用的校正檔；預設同 calibration_file（Mock 測試才分開）'),
        DeclareLaunchArgument('use_mock_serial', default_value='false',
                              description='測試用 Mock Serial（要搭配 mock 校正檔）'),
        DeclareLaunchArgument('env_cam_device', default_value='', description='環境相機裝置；空 = cameras.yaml'),
        DeclareLaunchArgument('arm1_cam_device', default_value='', description='手臂 1 鏡頭裝置；空 = cameras.yaml'),
        DeclareLaunchArgument('arm2_cam_device', default_value='', description='手臂 2 鏡頭裝置；空 = cameras.yaml'),
        DeclareLaunchArgument('calib_dir', default_value='', description='vision_pkg 校正檔目錄（空 = 預設）'),
        DeclareLaunchArgument('show_debug', default_value='false',
                              description='環境相機另開 OpenCV 辨識框視窗（需要桌面 DISPLAY）'),
        DeclareLaunchArgument('esp32_port', default_value='',
                              description='ESP32 吸盤序列埠（/dev/serial/by-id/...）；空 = 不啟動 micro-ROS agent'),
        DeclareLaunchArgument('esp32_reset_delay_s', default_value='3.0',
                              description='agent 啟動後幾秒自動重開 ESP32（RTS = EN）；0 = 不自動重開，要手動按 EN'),
        DeclareLaunchArgument('microros_setup', default_value='~/microros_ws/install/local_setup.bash',
                              description='micro-ROS agent 工作區的 local_setup.bash'),
        DeclareLaunchArgument('cycles', default_value='1', description='搬運幾件（1～8）'),
        DeclareLaunchArgument('journal_path', default_value='', description='任務紀錄檔；空 = 設定檔的路徑'),
        LogInfo(msg='PROTOTYPE：估計校正、沒有急停心跳、吸盤自動確認；CM-530 電源開關是唯一急停'),
        OpaqueFunction(function=micro_ros_agent), hardware, vision, coordinator,
    ])
