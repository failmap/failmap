[![Code Climate](https://codeclimate.com/github/failmap/admin/badges/gpa.svg)](https://codeclimate.com/github/failmap/admin) [![Build Status](https://travis-ci.org/failmap/admin.svg?branch=master)](https://travis-ci.org/failmap/admin) [![Test Coverage](https://codeclimate.com/github/failmap/admin/badges/coverage.svg)](https://codeclimate.com/github/failmap/admin/coverage)

# Support fail map
We keep organizations on their toes to protect everyone's data. Do you like this? Your donation insures continuous support, updates,
and new features. 

The Internet Cleanup Foundation helps cleaning up bad stuff on the web.

Donate to this project safely, easily and quickly by clicking on an amount below.

<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/5" target="_blank">&euro;5</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/10" target="_blank">&euro;10</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/25" target="_blank">&euro;20</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/50" target="_blank">&euro;50</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/100" target="_blank">&euro;100</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/200" target="_blank">&euro;200</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa/500" target="_blank">&euro;500</a>
<a href="https://useplink.com/payment/qaCyn8t6Tar7c5zVS6Fa" target="_blank">&euro;other</a>

# Requirements

Download and install git and python3 to get started.

- [git](https://git-scm.com/downloads)
- [python3](https://www.python.org/downloads/)


# Obtaining the software

In a directory of your choosing:
 
    sudo easy_install pip
    git clone https://github.com/failmap/admin/
    cd admin
    # if you need a specific branch, for example "mapwebsite"
    # git checkout mapwebsite

# Quickstart

It is advised to work within a Python virtualenv or use `direnv` (see below) to keep project
dependencies isolated and managed. (todo: how)

    pip3 install -e .
    failmap-admin migrate
    failmap-admin createsuperuser
    failmap-admin loaddata testdata  # slow, get a coffee   
    failmap-admin rebuild-ratings  # slow, also a tea
    failmap-admin runserver

Now visit the [website](http://127.0.0.1:8000/) and/or the 
[administrative interface ](http://127.0.0.1:8000/admin/) at http://127.0.0.1:8000


# Scanning services (beta)

Onboarding handles all new urls with an initial (fast) scan. The tls scanner slowly gets results
from qualys. Screenshot service makes many gigabytes of screenshots.

    failmap-admin onboard-service
    failmap-admin scan-tls-qualys-service
    failmap-admin screenshot-service

# Code quality / Testing

This project sticks to default pycodestyle/pyflakes configuration to maintain code quality.

To run code quality checks and unit tests run:

    tox

To make life easier you can use `autopep8`/`isort` before running `tox` to automatically fix most style issues:

    tox -e autofix

To run only a specific test use:

    tox -- -k test_name

To only run a specific test suite user for example:

    .tox/py34/bin/failmap-admin test tests/test_smarturl.py

To generate coverage report after tests in HTML run:

    coverage html
    open htmlcov/index.html

Pytest allows to drop into Python debugger when a tests fails. To enable run:

    tox -- --pdb

# Direnv / Virtualenv

This project has [direnv](https://direnv.net/) configuration to automatically manage the Python
virtual environment. Install direnv and run `direnv allow` to enable.

Alternatively you can manually create a virtualenv using:

    virtualenv venv

Be sure to active the environment before starting development every time:

    . venv/bin/activate

# Thanks to
This project is being maintained by the [Internet Cleanup Foundation](https://internetcleanup.foundation).
Special thanks to the SIDN Fonds for believing in this method of improving privacy.

Thanks to the many authors contributing to open software.