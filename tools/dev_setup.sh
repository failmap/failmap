#!/bin/bash

set -ve

# run all commands needed to setup dev. environment (like mentioned in README.md)

pip3 install -e .
failmap-admin migrate
# failmap-admin load-dataset dev_user
failmap-admin load-dataset testdata -v0
failmap-admin rebuild-ratings -v0
