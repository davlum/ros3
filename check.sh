#!/bin/bash
set -o errexit -o nounset -o pipefail

# Install dev requirements
pip install -r requirements-dev.txt -q

# run linter
flake8 ros3 test
pylint ros3 test

# run tests
pytest -vv
