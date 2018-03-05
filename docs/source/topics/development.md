# Development
Please follow the quickstart to get failmap on your system.

Additionally the Docker page could be very helpful.

## Code quality / Testing

This project sticks to default pycodestyle/pyflakes configuration to maintain code quality.

To run code quality checks and unit tests run:

    tox

For a comprehensive test run:

    tox -e check,test,datasets

To make life easier you can use `autopep8`/`isort` before running `tox` to automatically fix most style issues:

    tox -e autofix

To run only a specific test use:

    tox -e test -- -k test_name

To only run a specific test suite use for example:

    .tox/default/bin/failmap test tests/scanners/test_dummy.py

A coverage report is generated after running tests, on OSX it can be viewed using:

    open htmlcov/index.html

Pytest allows to drop into Python debugger when a tests fails. To enable run:

    tox -- --pdb

## Integration/system tests
Besides quality checks and unit tests there are also integration and system testing frameworks available.

These frameworks will run in the CI system but not by default when running `tox` due to their dependencies.

To run these testsuites make sure Docker is installed and running and run either:

    tox -e integration

or

    tox -e system

## Direnv / Virtualenv

This project has [direnv](https://direnv.net/) configuration to automatically manage the Python
virtual environment. Install direnv and run `direnv allow` to enable it initially. After this the environment will by automatically loaded/unloaded every time you enter/leave the project directory.

If you don't want to use Direnv be sure to source the `.envrc` file manually every time you want to work on the project:

    . .envrc
