from subprocess import check_output
from setuptools import find_packages, setup


def get_git_version():
    """Determine current version number from nearest git tag."""
    try:
        version = check_output(["git", "describe", "--tags", "--abbrev=0"]).rstrip().decode()
        develop = bool(check_output(["git", "status", "--porcelain"]).strip())
        if develop:
            return version + '.dev'
        else:
            return version
    except:
        return '0.0.0'


setup(
    name='failmap-admin',
    version=get_git_version(),
    packages=find_packages(),
    install_requires=open('requirements.txt').readlines(),
    entry_points={
        'console_scripts': [
            'failmap-admin = failmap_admin.manage:main',
        ],
    },
    include_package_data=True,
)
