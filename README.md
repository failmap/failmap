[![Code Climate](https://codeclimate.com/github/failmap/admin/badges/gpa.svg)](https://codeclimate.com/github/failmap/admin) [![Build Status](https://travis-ci.org/failmap/admin.svg?branch=master)](https://travis-ci.org/failmap/admin) [![Test Coverage](https://codeclimate.com/github/failmap/admin/badges/coverage.svg)](https://codeclimate.com/github/failmap/admin/coverage)

# Requirements

- Python3
- Tox

# Quickstart

It is advised to work within a Python virtualenv or use `direnv` (see below) to keep project dependencies isolated and managed.

    pip3 install -e .
    failmap-admin migrate
    failmap-admin loaddata testdata
    failmap-admin createsuperuser
    failmap-admin runserver

Now login at: http://127.0.0.1:8000/admin/

# Code quality / Testing

This project sticks to default pycodestyle/pyflakes configuration to maintain code quality.

To run code quality checks and unit tests run:

    tox

To make life easier you can use `autopep8`/`isort` before running `tox` to automatically fix most style issues:

    autopep8 -ri failmap_admin tests
    isort -rc failmap_admin tests

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

This project has [direnv](https://direnv.net/) configuration to automatically manage the Python virtual environment. Install direnv and run `direnv allow` to enable.

Alternatively you can manually create a virtualenv using:

    virtualenv venv

Be sure to active the environment before starting development every time:

    . venv/bin/activate

