#!/bin/bash

set -ve

# run all commands needed to setup dev. environment (like mentioned in README.md)

if -z "$VIRTUAL_ENV"; then
  echo "Refusing to run with a Virtualenv, please see README.md->Direnv/Virtualenv."
  exit 1
fi

pip3 install -e .
failmap migrate
# load development environment users/settings
failmap load-dataset development
# load a test data set
failmap load-dataset testdata -v0
failmap rebuild-ratings -v0
