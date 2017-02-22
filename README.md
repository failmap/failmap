[![Code Climate](https://codeclimate.com/github/failmap/admin/badges/gpa.svg)](https://codeclimate.com/github/failmap/admin)

# Requirement

- Python3

# Quickstart

    pip install -r requirements.txt
    ./manage.py migrate
    ./manage.py loaddata fail/fixtures/testdata.yaml
    ./manage.py createsuperuser
    ./manage.py runserver

Now login at: http://127.0.0.1:8000/admin/

# Code quality

This project sticks to default pycodestyle/pyflakes configuration to maintain code quality. To run code quality checks run:

    tox

To make life easier you can use `autopep8` before running `tox` to automatically fix most style issues:

    autopep8 -ri fail

# Direnv

This project uses [direnv](https://direnv.net/) to manage Python environment. Optionally install direnv and run `direnv allow` to enable.
