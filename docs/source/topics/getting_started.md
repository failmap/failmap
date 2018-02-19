# Getting Started

## System requirements

Linux or MacOS capable of running Python3 and git.

## Software Requirements

Download and install below system requirements to get started:

- [git](https://git-scm.com/downloads) (download and install)
- [python3.6](https://www.python.org/downloads/) (download and install)
- [Tox](http://tox.readthedocs.io/) (`pip3 install --user tox`)
- [direnv](https://direnv.net/) (download and install, then follow [setup instructions](https://direnv.net/), see Direnv section below)
- [Docker](https://docs.docker.com/engine/installation/) (recommended, follow instructions to install.)

## Quickstart

In a directory of your choosing:

    # download the software
    git clone --recursive https://gitlab.com/failmap/failmap/

    # enter the directory of the downloaded software
    cd failmap/

Using Direnv & Tox to manage environment (see Direnv section below). This prepares the shell environment for local development.

    direnv allow

Running Tox once creates a development Virtualenv in `.tox/default/` which is automatically used after creation due to Direnv setup. Running Tox without arguments by default also runs basic checks and tests to verify project code quality.

    tox

After completing succesfully the application is available to run:

    failmap -h

The following commands will start a complete developer instance of failmap with all required services.

    failmap devserver

Now visit the [map website](http://127.0.0.1:8000/) and/or the
[admin website](http://127.0.0.1:8000/admin/) at http://127.0.0.1:8000 (credentials: admin:faalkaart).

## Using the software

### The map website

The website is the site intended for humans. There are some controls on the website, such as the
time slider, twitter links and the possibilities to inspect organizations by clicking on them.

Using the map website should be straightforward.

### The admin website

Use the admin website to perform standard [data-operations](https://en.wikipedia.org/wiki/Create,_read,_update_and_delete),
run a series of actions on the data and read documentation of the internal workings of the failmap software.

The admin website is split up in four key parts:
1. Authentication and Authorization
This stores information about who can enter the admin interface and what they can do.

2. Map
Contains all information that is presented to normal humans.
This information is automatically filled based on the scans that have been performed over time.

3. Organizations
Lists of organizations, coordinates and internet adresses.

4. Scanners
Lists of endpoints and assorted scans on these endpoints.


## Troubleshooting getting started

If you need a specific branch, for example "mapwebsite"

    git checkout mapwebsite

This repository uses [submodules](https://git-scm.com/docs/git-submodule) to pull in
external dependencies. If you have not cloned the repository with `--recursive` or you need to
restore the submodules to the expected state run:

    git submodule update

## Development

### Code quality / Testing

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

### Integration/system tests
Besides quality checks and unit tests there are also integration and system testing frameworks available.

These frameworks will run in the CI system but not by default when running `tox` due to their dependencies.

To run these testsuites make sure Docker is installed and running and run either:

    tox -e integration

or

    tox -e system

### Direnv / Virtualenv

This project has [direnv](https://direnv.net/) configuration to automatically manage the Python
virtual environment. Install direnv and run `direnv allow` to enable it initially. After this the environment will by automatically loaded/unloaded every time you enter/leave the project directory.

If you don't want to use Direnv be sure to source the `.envrc` file manually every time you want to work on the project:

    . .envrc

## Known Issues

### Docker installation

#### ERROR: for failmap_database_1  Cannot start service database: Mounts denied:
As the error suggests, you're running the installation from a directory that is not shared with Docker. Change the docker configuration or run the installation from your user directory. You might receive this error if you run `docker-composer up` from /var/www/ or /srv/www/ as docker by default only has access to your user directory.


## Versioning

Version for the project is losely semver with no specific release schedule or meaning to version numbers (eg: stable/unstable).

Formal releases are created by creating a Git tag with the desired version number. These tags will trigger automated builds which will release the specified code under that version. Tags can be pushed from a local repository or created through the Gitlab interface: https://gitlab.com/failmap/failmap/tags/new

Informal releases are created by new commits pushed/merged to the master. The version number of the last formal release will be suffixed with the current short Git SHA.

For all releases artifacts will be created. Currently only Docker containers are pushed into the [registry](https://gitlab.com/failmap/failmap/container_registry). Each artifact will be tagged with the appropriate version (formal or informal). Where needed abstract tags will also be created/updated for these artifacts (eg: Docker build/staging/latest tags).

For local development informal release or a special `dev0` build release is used which indicates a different state from the formal releases.
