import os
import sys
from subprocess import check_output

from setuptools import find_packages, setup


def get_version():
    """Determine the most appropriate version number for this package."""

    # prefer explicit version provided by (docker) build environment
    if os.path.exists('version'):
        return open('version').read().strip()

    # try to use git tag if building python package
    try:
        # get closest tag version
        tag_version = check_output(["git", "describe", "--tags", "--abbrev=0"]).rstrip().decode()
        # determine if there has been development beyond the latest tagged commit
        dirty = bool(check_output(["git", "status", "--porcelain"]).strip())
        unreleased = bool(check_output(["git", "rev-list", tag_version + ".."]).strip())

        # there are unsaved changes
        if dirty:
            return tag_version + '.dev0'

        # the verion is commits ahead of latest tagged release
        if unreleased:
            # append git sha to version
            return tag_version + '+' + check_output("git rev-parse --short HEAD".split()).strip().decode()

        return tag_version
    except Exception as e:
        print("Failed to acquire version info from git: {e}".format(e=e), file=sys.stderr)
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
