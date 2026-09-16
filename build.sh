#!/bin/bash

pip install --upgrade pip

pip3 uninstall -y trpc_a2a

pip3 install -r requirements.txt

pip install -e .[all] -i https://pypi.org/simple/
