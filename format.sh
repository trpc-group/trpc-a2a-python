#!/bin/bash

python3 -m pip install --upgrade pip 

pip3 install yapf


# Find and format Python files.
find . -name "*.py" -not -path "./venv/*" \
                    -exec yapf -i {} \;
