import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'my_project_start'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='course',
    maintainer_email='course@example.com',
    description='Launch files for the course turtlesim project.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [],
    },
)
