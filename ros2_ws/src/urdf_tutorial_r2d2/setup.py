import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'urdf_tutorial_r2d2'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'urdf'), glob('urdf/*')),
        (os.path.join('share', package_name), glob('rviz/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='course',
    maintainer_email='course@example.com',
    description='R2D2 robot_state_publisher tutorial package.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'state_publisher = urdf_tutorial_r2d2.state_publisher:main',
        ],
    },
)
