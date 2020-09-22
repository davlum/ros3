#!/bin/bash
set -o errexit -o nounset -o pipefail

# run linter
pipenv run flake8 ros3 test
pipenv run pylint ros3 test
