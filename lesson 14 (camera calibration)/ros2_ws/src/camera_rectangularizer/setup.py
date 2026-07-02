from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'camera_rectangularizer'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Calibrated perspective rectangularization for ROS 2 images.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'rectangularizer = camera_rectangularizer.rectangularizer_node:main',
        ],
    },
)
