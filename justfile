# Testing echo across multiple python versions
# Run with:
# > just test
#
# Requisites:
# - uv (https://docs.astral.sh/uv/)
# - just (https://just.systems/man/en/)
#
# Warning:
# The 'uv run' command used in the recipe below, removes any existing uv-managed virtual environment
# and rebuilds it with the requested python version (passed with --python).
# Depending on the order of python versions in this script, this might result in the venv
# having a different python version that before the justfile recipe was run.
#
test:
    #!/usr/bin/env bash
    for version in 3.15 3.14 3.13 3.12; do  # This will leave the uv-managed venv with Python 3.12 installed
        echo "================================= Python $version ================================="
        uv run --python $version pytest -q || exit 1
    done
