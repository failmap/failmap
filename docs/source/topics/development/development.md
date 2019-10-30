# Development

Please follow the [quickstart](getting_started.md) to get Web Security Map on your system.

Additionally the [Docker](docker.md) page could be very helpful.

## A normal change to the software

This is an illustration to show a normal development practices.

We use git, which comes with many pitfalls. Just search your answer on stack exchange first and ask in the group later.

Make sure Web Security Map is up and running, by following the [getting started](getting_started.md) instructions. Then make a
branch that describes what you are doing. For example:

    git branch documentation_upgrade

Then make any changes to the source code. You'll see that the devserver automatically restarts after every save.

Once you're happy with your changes, and you've tested it on your environment using a meaningful dataset
(eg productiondata), then you can verify (and autofix) the code to our code standards:

    make fix

Fix any of the remarks it gives, otherwise your changes will not be added to the master branch.

You can only commit files to the master branch if you're up to date with it's code:

    git pull --rebase origin master

Follow the instructions on screen to fix merge conflicts if any.

When you are happy, review your changes and remove any temporary files using the instructions given:

    git status

If you like the files that are changed, add all changes to be merged:

    git add -A

Then commit them:

    git commit -m "a short description why you changed something"

Then push them to the server:

    git push

The push command will give you a link to file a merge request. Meanwhile the build servers are checking your code
before merging.

Follow the merge request link to create the actual merge request. Share it on the chat.websecuritymap.org channel for review
and feedback.

Once the feedback is processed (if needed at all) you can merge the code. If you can't, other members of the project can.
So ask.

## FAQ

### The web security map command won't start and i get some weird errors

Make sure you've got an up to date development environment. You can do so by running the following commands:

Rebuild the environment:

    make mrproper

Get all requirements and development requirements:

    make setup

## Code quality / Testing

This project sticks to default pycodestyle/pyflakes configuration to maintain code quality.

To run code quality checks and unit tests run:

    make

For a comprehensive test run:

    make check test test_datasets

To make life easier you can use `autopep8`/`isort` before running `make` to automatically fix most style issues:

    make fix

To run only a specific test use:

    make test testargs="-k test_name"

To only run a specific test suite use for example:

    make test testargs=tests/scanners/test_dummy.py

A coverage report is generated after running tests, on OSX it can be viewed using:

    open htmlcov/index.html

Pytest allows to drop into Python debugger when a tests fails. To enable run:

    make testargs=--pdb

## Integration/system tests

Besides quality checks and unit tests there are also integration and system testing frameworks available.

These frameworks will run in the CI system but not by default when running `make` due to their dependencies.

To run these testsuites make sure Docker is installed and running and run either:

    make test_integration

or

    make test_system

## Direnv / Virtualenv

This project has [direnv](https://direnv.net/) configuration to automatically manage the Python
virtual environment. Install direnv and run `direnv allow` to enable it initially. After this the environment will by automatically loaded/unloaded every time you enter/leave the project directory.

If you don't want to use Direnv be sure to source the `.envrc` file manually every time you want to work on the project:

    . .envrc

## Python dependencies managment

Dependencies and settings for this project are managed using [Pip-tools](https://github.com/jazzband/pip-tools) which is simple tool build on top of Pip and `requirements.txt` files.

Dependencies are added to (or removed from) the `requirements.in` file (`requirements-dev.in` for development dependencies). The `pip-compile` command will then be used to parse this file and generate a list of all (recursive)dependencies to install with exact versions pinnen and put this in the respective `.txt` file.

Any update to a `.in` file will automatically trigger a Make target to update `.txt` files and install new dependencies when running Make commands.

Version pinning in `.in` files should be kept to a minimum and if it is required should be accompanied by a rationale/deadline comment.

To have `pip-compile` check for new versions of all dependencies within the version boundaries of `.in` files run: `make update_requirements`

Both the `.in` and the `.txt` files should be commited to Git. The `.txt` files are used during installation to ensure dependencies are predictable accross environments.
