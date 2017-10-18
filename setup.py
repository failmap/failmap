import os
from subprocess import check_output
from setuptools import find_packages, setup


def get_version():
    """Determine current version number from nearest git tag."""

    # prefer explicit version provided by (docker) build environment
    try:
        return open('version').read().strip()
    except Exception:
        pass

    # fallback to git tag if building python package
    try:
        # get closest tag version
        version = check_output(["git", "describe", "--tags", "--abbrev=0"]).rstrip().decode()
        # determine if there has been development beyond the tagged commit
        dirty = bool(check_output(["git", "status", "--porcelain"]).strip())
        unpushed = bool(check_output(["git", "rev-list", "origin/master.."]).strip())
        develop = dirty or unpushed

        if develop:
            return version + '.dev'
        else:
            return version
    except Exception:
        pass

    # fallback
    return '0.0.0'


setup(
    name='failmap-admin',
    version=get_version(),
    packages=find_packages(),
    install_requires=open('requirements.txt').readlines(),
    entry_points={
        'console_scripts': [
            'failmap-admin = failmap_admin.manage:main',
        ],
    },
    include_package_data=True,
)
