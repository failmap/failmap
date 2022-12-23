SHELL=/bin/bash

# settings
app_name = websecmap

# configure virtualenv to be created in OS specific cache directory
ifeq ($(shell uname -s),Darwin)
# macOS cache location
CACHEDIR ?= ~/Library/Caches
else
# User customized cache location or Linux default
XDG_CACHE_HOME ?= ~/.cache
CACHEDIR ?= ${XDG_CACHE_HOME}
endif
VIRTUAL_ENV ?= ${CACHEDIR}/virtualenvs/$(notdir ${PWD})

# variables for environment
bin = ${VIRTUAL_ENV}/bin

# shortcuts for common used binaries
python = ${bin}/python
pip = ${bin}/pip
pip-compile = ${bin}/pip-compile
pip-sync = ${bin}/pip-sync

# python binary used to create virtual environment
base_python ?= python3.11

# application binary
app = ${bin}/${app_name}

ifeq (${MAKECMDGOALS},)
$(info Virtualenv path: ${VIRTUAL_ENV})
$(info Run App: websecmap)
$(info )
$(info Run `make help` for available commands or use tab-completion.)
$(info )
$(info Running complete setup and test of development environment now.)
$(info )
endif

pysrcdirs = ${app_name}/ tests/
pysrc = $(shell find ${pysrcdirs} -name \*.py)
shsrc = $(shell find * ! -path vendor\* -name \*.sh)

.PHONY: test check check_migrations setup run fix autofix clean mrproper test_integration

# default action to run
all: setup test coverage check

# setup entire dev environment
setup: ${app}	## setup development environment and application
	@test \! -z "$$PS1" || (echo -ne "Development environment is tested and ready."; \
	if command -v websecmap &>/dev/null;then \
		echo -e " Development shell is activated."; \
	else \
		echo -e "\n\nTo activate development shell run:"; \
		echo -e "\n\t. ${VIRTUAL_ENV}/bin/activate$$([[ "$$SHELL" =~ "fish" ]] && echo .fish)\n"; \
		echo -e "Or refer to Direnv in README.md for automatic activation."; \
	fi)

# install application and all its (python) dependencies
${app}: ${VIRTUAL_ENV}/.requirements.installed | ${pip}
	# install project and its dependencies
	${pip} install --no-deps --editable .
	@test -f $@ && touch $@  # update timestamp, do not create empty file

# run tests with coverage, and generate coverage report
coverage: enable_coverage=coverage run -m
coverage: test
	# generate pretty html coverage `htmlcov/index.html`
	coverage html
	# generate coverage report
	coverage report

test: ${pysrc} ${app} ## run test suite
	# run testsuite
	${enable_coverage} pytest --verbose -ra -k 'not integration_celery and not integration_scanners and not system' ${testargs}

test-parallel: ${pysrc} ${app} ## run test suite
	# This is experimental
	# run testsuite in parallel using xdist. This does not work during build and makes for a slower build even.
	# -n comes from pytest-xdist, no longer name possible. Docs: https://pytest-xdist.readthedocs.io/en/latest/distribution.html
	# -n auto comes with celery errors and also eats up more time to spin up workers than it takes to test.
	${enable_coverage} pytest -n 4 --verbose -ra -k 'not integration_celery and not integration_scanners and not system' ${testargs}

# all quality assurance commands before pushing new code
qa: autofix test

check: check_py check_migrations check_sh  ## code quality checks
check_py: ${pysrc} ${app}
	# check code quality
	pylama .
	# check formatting
	black --check .

check_migrations: ${pysrc} ${app}
	# ensure no model updates are commited without migrations
	${app} makemigrations --check

check_sh: ${shsrc}
	# shell script checks (if installed)
	if command -v shellcheck &>/dev/null;then shellcheck --version; shellcheck ${shsrc}; fi

autofix fix: .make.fix  ## automatic fix of trivial code quality issues
.make.fix: ${pysrc} ${app}
	# remove unused imports
	autoflake .
	# autoformat code
	black .
	# do a check after autofixing to show remaining problems
	${MAKE} check
	@touch $@  # update timestamp

run: ${app}  ## run complete application stack (frontend, worker, broker)
	# start server (this can take a while)
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} devserver

audit: ${app}
	${python} -m bandit --configfile pyproject.toml --recursive websecmap

run_no_backend: ${app}  ## run application stack without broker/worker
	# start server (this can take a while)
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} devserver --no-backend

run-frontend: ${app}  ## only run frontend component
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} runserver

run-nonlocal-frontend: ${app}  ## only run frontend component
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} runserver 0.0.0.0:8000

app: ${app}  ## perform arbitrary app commands
    # make app cmd="help"
    # make app cmd="report -y municipality"
    # make app cmd="makemigrations"
    # make app cmd="migrate"
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} ${cmd}

run-worker: ${app}  ## only run worker component
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} celery worker -ldebug

run-broker:  ## only run broker
	docker run --rm --name=redis -p 6379:6379 redis

testcase: ${app}
	# run specific testcase
	# example: make testcase case=test_openstreetmaps
	DB_NAME=test.sqlite3 pytest -W ignore::django.utils.deprecation.RemovedInDjango40Warning -vvv --log-cli-level=10 -k ${case}

test_integration: ${app}
	# run integration tests
	# see docs at make test why the -k option is so explicit (no globbing anymore).
	DB_NAME=test.sqlite3 \
		pytest -vv -ra -k 'integration_celery or integration_scanners' ${testargs}

test_system:
	@if [ -z "$IMAGE" ];then echo "Must provide Docker image variable IMAGE, to test against!"; exit 1; fi
	# run system tests
	pytest --verbose tests/system ${testargs}

test_datasets: ${app}
	/bin/sh -ec "find websecmap -path '*/fixtures/*.json' -print0 | \
		xargs -0n1 basename -s .yaml | uniq | \
		xargs -n1 ${app} test_dataset"

test_deterministic: | ${VIRTUAL_ENV}
	/bin/bash tools/compare_differences.sh HEAD HEAD tools/show_ratings.sh testdata

test_mysql:
	docker run --name mysql -d --rm -p 3306:3306 \
		-e MYSQL_ROOT_PASSWORD=failmap \
		-e MYSQL_DATABASE=failmap \
		-e MYSQL_USER=failmap \
		-e MYSQL_PASSWORD=failmap \
		-v $$PWD/tests/etc/mysql-minimal-memory.cnf:/etc/mysql/conf.d/mysql.cnf \
		mysql:5.6
	DJANGO_DATABASE=production DB_USER=root DB_HOST=127.0.0.1 \
		$(MAKE) test; e=$$?; docker stop mysql; exit $$e

test_postgres:
	docker run --name postgres -d --rm -p 5432:5432 \
		-e POSTGRES_DB=failmap \
		-e POSTGRES_USER=root \
		-e POSTGRES_PASSWORD=failmap \
		postgres:9.5
	DJANGO_DATABASE=production DB_ENGINE=postgresql_psycopg2 DB_USER=root DB_HOST=127.0.0.1 \
		$(MAKE) test; e=$$?; docker stop postgres; exit $$e

clean:  ## cleanup build artifacts, caches, databases, etc.
	# remove python cache files
	-find * -name __pycache__ -print0 | xargs -0 rm -rf
	# remove state files
	-rm -f .make.*
	# remove test artifacts
	-rm -rf .pytest_cache htmlcov/
	# remove build artifacts
	-rm -rf *.egg-info dist/ pip-wheel-metadata/
	# remove runtime state files
	-rm -rf *.sqlite3

clean_virtualenv:  ## cleanup virtualenv and installed app/dependencies
	# remove virtualenv
	-rm -fr ${VIRTUAL_ENV}/

mrproper: clean clean_virtualenv ## thorough cleanup, also removes virtualenv

${VIRTUAL_ENV}/.requirements.installed: requirements.txt requirements-dev.txt| ${pip-sync}
	${pip-sync} $^
	@touch $@  # update timestamp

requirements = requirements.txt requirements-dev.txt requirements-deploy.txt
requirements: ${requirements}

# perform 'pip freeze' on first class requirements in .in files.
requirements.txt: requirements.in | ${pip-compile}
	${pip-compile} ${pip_compile_args} --output-file $@ $<

requirements-dev.txt: requirements-dev.in requirements.in | ${pip-compile}
	${pip-compile} ${pip_compile_args} --output-file $@ $<

pip-sync:
	# synchronizes the .venv with the state of requirements.txt
	python3 -m piptools sync requirements.txt requirements-dev.txt

update_requirements: pip_compile_args=--upgrade
update_requirements: _mark_outdated requirements.txt requirements-dev.txt requirements-deploy.txt _commit_update

upgrade_package: | ${pip-compile} ## upgrade a single Python package in requirements.txt
	@if [ -z "${package}"];then echo "Usage: make upgrade_package package=package-name"; exit 1; fi
	${pip-compile} requirements.in --upgrade-package ${package}

upgrade_dev_package: | ${pip-compile} ## upgrade a single Python package in requirments-dev.txt
	@if [ -z "${package}"];then echo "Usage: make upgrade_dev_package package=package-name"; exit 1; fi
	${pip-compile} requirements-dev.in --upgrade-package ${package}

upgrade_deploy_package: | ${pip-compile} ## upgrade a single Python package in requirements-deploy.txt
	@if [ -z "${package}"];then echo "Usage: make upgrade_deploy_package package=package-name"; exit 1; fi
	${pip-compile} requirements-deploy.in --upgrade-package ${package}

_mark_outdated:
	touch requirements*.in

_commit_update: requirements.txt
	git add requirements*.txt requirements*.in
	git commit -m "Updated requirements."

${pip-compile} ${pip-sync}: | ${pip}
	# importlib 5 has issues with AttributeError: 'EntryPoints' object has no attribute 'get' in python 3.7
	# the changelog says they have removed some shims.
	${pip} install --quiet pip-tools "importlib-metadata<5"

${python} ${pip}:
	@if ! command -v ${base_python} &>/dev/null;then \
		echo "Python 3 is not available. Please refer to installation instructions in README.md"; \
	fi
	# create virtualenv
	${base_python} -mvenv ${VIRTUAL_ENV}

# utility
help:           ## Show this help.
	@IFS=$$'\n' ; \
	help_lines=(`fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##/:/'`); \
	printf "\nRun \`make\` with any of the targets below to reach the desired target state.\n" ; \
	printf "\nTargets are complementary. Eg: the \`run\` target requires \`setup\` which is automatically executed.\n\n" ; \
	printf "%-30s %s\n" "target" "help" ; \
	printf "%-30s %s\n" "------" "----" ; \
	for help_line in $${help_lines[@]}; do \
		IFS=$$':' ; \
		help_split=($$help_line) ; \
		help_command=`echo $${help_split[0]} | sed -e 's/^ *//' -e 's/ *$$//'` ; \
		help_info=`echo $${help_split[2]} | sed -e 's/^ *//' -e 's/ *$$//'` ; \
		printf '\033[36m'; \
		printf "%-30s %s" $$help_command ; \
		printf '\033[0m'; \
		printf "%s\n" $$help_info; \
	done

check-commit: fix test

lint:  ${pysrc} ${app} ## Do basic linting
	pylint ${pysrcdirs}

isort:  ${pysrc} ${app}
	isort -rc ${pysrcdirs}
