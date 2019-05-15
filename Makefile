# settings
app_name = websecmap
commands = devserver rebuild_reports

# configure virtualenv to be created in OS specific cache directory
ifeq ($(UNAME_S),Darwin)
# macOS cache location
CACHEDIR ?= ~/Library/Caches
else
# User customized cache location or Linux default
XDG_CACHE_HOME ?= ~/.cache
CACHEDIR ?= ${XDG_CACHE_HOME}
endif
VIRTUAL_ENV ?= ${CACHEDIR}/virtualenvs/$(notdir ${PWD})
$(info Virtualenv path: ${VIRTUAL_ENV})

$(info )

# shortcuts for common used binaries
bin = ${VIRTUAL_ENV}/bin
env = PATH=${bin}:$$PATH
python = ${bin}/python
pip = ${bin}/pip
poetry = ${bin}/poetry

# application binary
app = ${bin}/${app_name}

pysrcdirs = ${app_name}/ tests/
pysrc = $(shell find ${pysrcdirs} -name *.py)
shsrc = $(shell find * ! -path vendor\* -name *.sh)

.PHONY: ${commands} test check setup run fix autofix clean mrproper poetry test_integration

# default action to run
all: check test

# setup entire dev environment
setup: ${app}

# install application and all its (python) dependencies
${app}: poetry.lock | poetry
	# install project and its dependencies
	VIRTUAL_ENV=${VIRTUAL_ENV} ${poetry} install --develop=$(notdir ${app}) ${poetry_args}
	@test -f $@ && touch $@

poetry.lock: pyproject.toml | poetry
	# update package version lock
	${env} poetry lock

test: .make.test
.make.test: ${pysrc} ${app}
	# run testsuite
	DJANGO_SETTINGS_MODULE=${app_name}.settings ${env} coverage run --include '${app_name}/*' \
		-m pytest -k 'not integration and not system' ${testargs}
	# generate coverage
	${env} coverage report
	# and pretty html
	${env} coverage html
	# ensure no model updates are commited without migrations
	${app} makemigrations --check
	@touch $@

check: .make.check.py .make.check.sh
.make.check.py: ${pysrc} ${app}
	# check code quality
	${env} pylama ${pysrcdirs} --skip "**/migrations/*"
	@touch $@

.make.check.sh: ${shsrc}
	# shell script checks (if installed)
	if command -v shellcheck &>/dev/null;then shellcheck ${shsrc}; fi
	@touch $@

autofix fix: .make.fix
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

run: ${app}
	# start server (this can take a while)
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} devserver

test_integration: ${app}
  	DB_NAME=test.sqlite3 ${run} pytest -v -k 'integration' ${testargs}

${commands}: ${app}
	${app} $@ ${args}

test_integration: ${app}
	# run integration tests
	${env} DJANGO_SETTINGS_MODULE=${app_name}.settings DB_NAME=test.sqlite3 \
		${env} pytest -k 'integration' ${testargs}

test_system:
	# run system tests
	${env} pytest tests/system ${testargs}

test_datasets: ${app}
	/bin/sh -ec "find websecmap -path '*/fixtures/*.yaml' -print0 | \
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
		postgres:9.4
	DJANGO_DATABASE=production DB_ENGINE=postgresql_psycopg2 DB_USER=root DB_HOST=127.0.0.1 \
		$(MAKE) test; e=$$?; docker stop postgres; exit $$e

# cleanup build artifacts, caches, etc.
clean:
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

# thorough clean, remove virtualenv
mrproper: clean
	-rm -fr ${VIRTUAL_ENV}/

# don't let poetry manage the virtualenv, we do it ourselves to make it deterministic
poetry: ${poetry}
poetry_version=0.12.15
${poetry}: ${python}
	# install poetry
	${pip} install -q poetry==${poetry_version}

${python}:
	@if ! command -v python3 &>/dev/null;then \
		echo "Python 3 is not available. Please refer to installation instructions in README.md"; \
	fi
	# create virtualenv
	python3 -mvenv ${VIRTUAL_ENV}
