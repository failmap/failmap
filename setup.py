from setuptools import find_packages, setup

setup(
    name='failmap-admin',
    version='0.1',
    packages=find_packages(),
    install_requires=open('requirements.txt').readlines(),
    entry_points={
        'console_scripts': [
            'failmap-admin = failmap_admin.manage:main',
        ],
    },
    include_package_data=True,
)
