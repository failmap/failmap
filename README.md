[![Code Climate](https://codeclimate.com/github/failmap/admin/badges/gpa.svg)](https://codeclimate.com/github/failmap/admin) [![Build Status](https://travis-ci.org/failmap/admin.svg?branch=master)](https://travis-ci.org/failmap/admin)

# Requirement

- Python3

# Quickstart

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

To make life easier you can use `autopep8` before running `tox` to automatically fix most style issues:

    autopep8 -ri fail

Failing tests can be debugged interactively using:

    tox -- --pdb

# Direnv

This project uses [direnv](https://direnv.net/) to manage Python environment. Optionally install direnv and run `direnv allow` to enable.
