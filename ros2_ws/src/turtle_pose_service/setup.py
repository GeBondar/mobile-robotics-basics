from setuptools import find_packages, setup

package_name = 'turtle_pose_service'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='course',
    maintainer_email='course@example.com',
    description='Turtlesim pose service server and client.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'pose_server = turtle_pose_service.pose_server:main',
            'pose_client = turtle_pose_service.pose_client:main',
        ],
    },
)
