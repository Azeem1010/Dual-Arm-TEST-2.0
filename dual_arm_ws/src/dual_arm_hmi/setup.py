from setuptools import find_packages, setup

setup(
    name='dual_arm_hmi',
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/dual_arm_hmi']),
        ('share/dual_arm_hmi', ['package.xml']),
    ],
    install_requires=['setuptools'],
    entry_points={'console_scripts': [
        'hmi = dual_arm_hmi.app:main',
        'hmi_screenshots = dual_arm_hmi.tools.capture_screens:main',
    ]},
)
