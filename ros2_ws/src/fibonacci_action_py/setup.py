from setuptools import find_packages, setup

package_name = 'fibonacci_action_py'

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
    description='Python Fibonacci action server and client.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'fibonacci_action_server = fibonacci_action_py.fibonacci_action_server:main',
            'fibonacci_action_client = fibonacci_action_py.fibonacci_action_client:main',
        ],
    },
)
