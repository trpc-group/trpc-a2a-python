#!/bin/sh

INIT_PY="trpc_a2a/version.py"

version=$(grep -oP "__version__ = '\K[^']+" "$INIT_PY")

echo "version is ${version}"

sh +x build.sh


# pip3 install urllib3==1.26.6

pip3 install twine
sudo rm -rf dist/

pip3 install urllib3
pip install build
# dist source package
#python -m build --sdist
# dist wheel pacakge
python -m build


twine upload dist/* -r tencent
