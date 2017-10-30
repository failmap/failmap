#!/bin/bash

set -ve

# run all commands needed to setup dev. environment (like mentioned in README.md)

if -z "$VIRTUAL_ENV"; then
  echo "Refusing to run with a Virtualenv, please see README.md->Direnv/Virtualenv."
  exit 1
fi

pip3 install -e .
failmap-admin migrate
# load development environment users/settings
failmap-admin load-dataset development
# load a test data set
failmap-admin load-dataset testdata -v0
failmap-admin rebuild-ratings -v0
