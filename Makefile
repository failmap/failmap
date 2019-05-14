SHELL = /bin/bash

# configure virtualenv to be created in OS specific cache directory
ifeq ($(UNAME_S),Darwin)
# macOS cache location
CACHEDIR ?= ~/Library/Caches
else
# User customized cache location or Linux default
XDG_CACHE_HOME ?= ~/.cache
CACHEDIR ?= ${XDG_CACHE_HOME}
endif
VIRTUAL_ENV = ${CACHEDIR}/virtualenvs/$(notdir ${PWD})
$(info Virtualenv path: ${VIRTUAL_ENV})

$(info )

# shortcuts for common used binaries
bin = ${VIRTUAL_ENV}/bin
python = ${bin}/python
pip = ${bin}/pip
poetry = ${bin}/poetry

# application binary
app = ${bin}/websecmap

commands = devserver rebuild_reports

src = $(shell find * -name *.py)

.PHONY: ${commands} test check setup run fix autofix clean mrproper poetry test_integration

# default action to run
all: check test

# setup entire dev environment
setup: | ${app}

# install application and all its (python) dependencies
${app}: poetry.lock | poetry
	# install project and its dependencies
	VIRTUAL_ENV=${VIRTUAL_ENV} ${poetry} install --develop=$(notdir ${app})
	test -f $@ && touch $@

test: .make.test
.make.test: ${src} | setup
	# run testsuite
	DJANGO_SETTINGS_MODULE=websecmap.settings ${bin}/coverage run --include 'websecmap/*' \
		-m pytest -v -k 'not integration and not system' ${testargs}
	# generate coverage
	${bin}/coverage report
	# and pretty html
	${bin}/coverage html
	# ensure no model updates are commited without migrations
	${app} makemigrations --check
	@touch $@

check: .make.check
.make.check: ${src} | setup
	# check code quality
	${bin}/pylama websecmap tests --skip "**/migrations/*"
	@touch $@

autofix fix: .make.fix
.make.fix: ${src} | setup
	# fix trivial pep8 style issues
	${bin}/autopep8 -ri websecmap tests
	# remove unused imports
	${bin}/autoflake -ri --remove-all-unused-imports websecmap tests
	# sort imports
	${bin}/isort -rc websecmap tests
	# do a check after autofixing to show remaining problems
	${MAKE} check
	@touch $@

run: | setup
	# start server (this can take a while)
	DEBUG=1 NETWORK_SUPPORTS_IPV6=1 ${app} devserver

${commands}: | setup
	${app} $@ ${args}

test_integration: | setup
	# run integration tests
	DB_NAME=test.sqlite3 ${bin}/pytest -v -k 'integration' ${testargs}

test_system:
	# run system tests
	${bin}/pytest -v tests/system ${testargs}

test_datasets: | setup
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
	find * -name __pycache__ -print0 | xargs -0 rm -rf
	# remove state files
	rm -f .make.*
	# remove test artifacts
	rm -rf .pytest_cache htmlcov/
	# remove build artifacts
	rm -rf *.egg-info dist/ pip-wheel-metadata/
	# remove runtime state files
	rm -rf *.sqlite3

# thorough clean, remove virtualenv
mrproper: clean
	rm -fr ${VIRTUAL_ENV}/

# don't let poetry manage the virtualenv, we do it ourselves to make it deterministic
poetry: ${VIRTUAL_ENV}/bin/poetry
poetry_version=0.12.15
${VIRTUAL_ENV}/bin/poetry: ${python}
	# install poetry
	${pip} install -q poetry==${poetry_version}

${python}:
	@if ! command -v python3.6 &>/dev/null;then \
		echo "Python 3.6 is not avaiable. Please refer to installation instructions in README.md"; \
	fi
	# create virtualenv
	python3.6 -mvenv ${VIRTUAL_ENV}
