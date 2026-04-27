from setuptools import find_packages, setup

package_name = 'my_turtle_subscriber'

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
    description='Standalone turtlesim pose subscriber.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'turtle_subscriber = my_turtle_subscriber.turtle_subscriber:main',
        ],
    },
)
