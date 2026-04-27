from setuptools import find_packages, setup

package_name = 'my_turtle_controller'

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
    description='Turtlesim publisher/subscriber examples for the course.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'turtle_publisher = my_turtle_controller.turtle_publisher:main',
            'turtle_subscriber = my_turtle_controller.turtle_subscriber:main',
            'number_publisher = my_turtle_controller.number_publisher:main',
            'turtle_action_server = my_turtle_controller.turtle_action_server:main',
            'turtle_action_client = my_turtle_controller.turtle_action_client:main',
        ],
    },
)
