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
$(info Virtualenv path: ${VIRTUAL_ENV})

# variables for environment
bin = ${VIRTUAL_ENV}/bin
env = env PATH=${bin}:$$PATH

# shortcuts for common used binaries
python = ${bin}/python
pip = ${bin}/pip
pip-compile = ${bin}/pip-compile
pip-sync = ${bin}/pip-sync

# application binary
app = ${bin}/${app_name}

$(info Run App: ${env} ${app})
$(info )
$(info Run `make help` for available commands or use tab-completion.)
$(info )

pysrcdirs = ${app_name}/ tests/
pysrc = $(shell find ${pysrcdirs} -name *.py)
shsrc = $(shell find * ! -path vendor\* -name *.sh)

.PHONY: test check setup run fix autofix clean mrproper test_integration

# default action to run
all: check test setup

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
	${python} setup.py develop --no-deps
	@test -f $@ && touch $@

test: .make.test	## run test suite
.make.test: ${pysrc} ${app}
	# run testsuite
	# #7040: -k no longer matches against the names of the directories outside the test session root.
	# #7122: Expressions given to the -m and -k options are no longer evaluated using Python’s eval().
	# The format supports or, and, not, parenthesis and general identifiers to match against.
	# Python constants, keywords or other operators are no longer evaluated differently.
	DJANGO_SETTINGS_MODULE=${app_name}.settings ${env} coverage run --include '${app_name}/*' --omit '*migrations*' \
		-m pytest -vv -ra -k 'not integration_celery and not integration_scanners and not system' ${testargs}
	# generate coverage
	${env} coverage report
	# and pretty html
	${env} coverage html
	# ensure no model updates are commited without migrations
	${env} ${app} makemigrations --check
	@touch $@

check: .make.check.py .make.check.sh  ## code quality checks
.make.check.py: ${pysrc} ${app}
	# check code quality
	${env} pylama ${pysrcdirs} --skip "**/migrations/*"
	@touch $@

.make.check.sh: ${shsrc}
	# shell script checks (if installed)
	if command -v shellcheck &>/dev/null;then ${env} shellcheck --version; ${env} shellcheck ${shsrc}; fi
	@touch $@

autofix fix: .make.fix  ## automatic fix of trivial code quality issues
.make.fix: ${pysrc} ${app}
	# fix trivial pep8 style issues
	${env} autopep8 -ri ${pysrcdirs}
	# remove unused imports
	${env} autoflake -ri --remove-all-unused-imports ${pysrcdirs}
	# sort imports
	${env} isort -rc ${pysrcdirs}
	# do a check after autofixing to show remaining problems
	${MAKE} check
	@touch $@

run: ${app}  ## run complete application stack (frontend, worker, broker)
	# start server (this can take a while)
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${env} ${app} devserver

run_no_backend: ${app}  ## run application stack without broker/worker
	# start server (this can take a while)
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${env} ${app} devserver --no-backend

run-frontend: ${app}  ## only run frontend component
	DEBUG=1 DJANGO_SETTINGS_MODULE=${app_name}.settings NETWORK_SUPPORTS_IPV6=1 ${env} ${app} runserver

run-nonlocal-frontend: ${app}  ## only run frontend component
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${env} ${app} runserver 0.0.0.0:8000

app: ${app}  ## perform arbitrary app commands
    # make app cmd="help"
    # make app cmd="report -y municipality"
    # make app cmd="makemigrations"
    # make app cmd="migrate"
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${env} ${app} ${cmd}

run-worker: ${app}  ## only run worker component
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${env} ${app} celery worker -ldebug

run-broker:  ## only run broker
	docker run --rm --name=redis -p 6379:6379 redis

testcase: ${app}
	# run specific testcase
	# example: make testcase case=test_openstreetmaps
	${env} DJANGO_SETTINGS_MODULE=${app_name}.settings DB_NAME=test.sqlite3 \
		${env} pytest -vv --log-cli-level=10 -k ${case}

test_integration: ${app}
	# run integration tests
	# see docs at make test why the -k option is so explicit (no globbing anymore).
	${env} DJANGO_SETTINGS_MODULE=${app_name}.settings DB_NAME=test.sqlite3 \
		${env} pytest -vv -ra -k 'integration_celery or integration_scanners' ${testargs}

test_system:
	# run system tests
	${env} pytest -vv --setup-show tests/system ${testargs}

test_datasets: ${app}
	${env} /bin/sh -ec "find websecmap -path '*/fixtures/*.json' -print0 | \
		xargs -0n1 basename -s .yaml | uniq | \
		xargs -n1 ${app} test_dataset"

test_deterministic: | ${VIRTUAL_ENV}
	${env} /bin/bash tools/compare_differences.sh HEAD HEAD tools/show_ratings.sh testdata

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
	@touch $@

# perform 'pip freeze' on first class requirements in .in files.
requirements.txt requirements-dev.txt: %.txt: %.in | ${pip-compile}
	${pip-compile} ${pip_compile_args} --output-file $@ $<

update_requirements: pip_compile_args=--upgrade
update_requirements: _mark_outdated requirements.txt requirements-dev.txt _commit_update

_mark_outdated:
	touch requirements*.in

_commit_update: requirements.txt
	git add requirements*.txt requirements*.in
	git commit -m "Updated requirements."

${pip-compile} ${pip-sync}: | ${pip}
	${pip} install --quiet pip-tools

${python} ${pip}:
	@if ! command -v python3 &>/dev/null;then \
		echo "Python 3 is not available. Please refer to installation instructions in README.md"; \
	fi
	# create virtualenv
	python3 -mvenv ${VIRTUAL_ENV}

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
