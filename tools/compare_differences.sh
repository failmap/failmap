#!/usr/bin/env bash

set -ex

# Compare output of a test script run against two different branches.

# This script will checkout a the specified branches, create a clean database and rebuild ratings
# after which a script is used to generate output. This output can then be compared for discrepancies.

# usage: tools/compare_differences.sh <branch1> <branch2> <test_script> [<dataset-name>]

branches=(${1?First argument needs to be branch name} ${2?Second argument needs to be branch name})
test_script=${3?Last argument needs to be test script}
dataset=${4:-productiondata}

for branch in "${branches[@]}"; do
  git checkout "$branch"
  # prepare database
  export DB_NAME=$branch.sqlite3
  test -f "$DB_NAME" && rm "$DB_NAME"
  failmap-admin migrate -v0

  # load dataset and update ratings
  failmap-admin load-dataset -v0 "$dataset"
  failmap-admin rebuild-ratings -v0

  # create output
  "$test_script" > "$branch.out"
done

# compare output
sdiff "${branches[@]/%/.out}" | less
