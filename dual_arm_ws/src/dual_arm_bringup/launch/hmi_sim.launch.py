"""Everything the operator interface shows in simulation.

The Gazebo task, the three vision nodes publishing their annotated images, and the
calibration status monitor. The task still decides zones from Gazebo ground truth.
"""
from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    calib_dir = LaunchConfiguration('calib_dir')
    launch_dir = share('dual_arm_bringup') + '/launch/'
    actions = [
        DeclareLaunchArgument('gz_args', default_value='-r -s'),
        DeclareLaunchArgument('cycles', default_value='1'),
        DeclareLaunchArgument('prefilled_slots', default_value='2'),
        DeclareLaunchArgument('journal_path', default_value=''),
        DeclareLaunchArgument('calib_dir', default_value='~/.ros/dual_arm_calib/sim'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_dir + 'demo_pick_place.launch.py'), launch_arguments={
            'gz_args': LaunchConfiguration('gz_args'), 'cycles': LaunchConfiguration('cycles'),
            'prefilled_slots': LaunchConfiguration('prefilled_slots'), 'journal_path': LaunchConfiguration('journal_path'),
        }.items()),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_dir + 'calibration.launch.py'),
                                 launch_arguments={'calib_dir': calib_dir}.items()),
    ]
    for name in ('env', 'arm1', 'arm2'):
        overrides = {'use_sim_time': True, 'show_debug': False, 'publish_debug_image': True, 'calib_dir': calib_dir}
        if name == 'env':
            # The simulated overhead camera sees zone A on the image left (A|B|C); see vision_sim.launch.py.
            overrides['field.reverse'] = True
        actions.append(Node(package='vision_pkg', executable=f'{name}_vision_node', output='screen', parameters=[
            f'{share("vision_pkg")}/config/{name}_vision.yaml', overrides]))
    return LaunchDescription(actions)
