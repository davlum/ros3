#!/bin/bash
set -o errexit -o nounset -o pipefail

# run linter
./lint.sh

# run tests
pipenv run pytest -vv
