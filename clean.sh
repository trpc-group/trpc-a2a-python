#!/bin/bash

sudo rm  -rf  coverage.xml
sudo rm  -rf  *.log
sudo rm  -rf  htmlcov
sudo rm  -rf  .coverage
sudo rm  -rf  .__*
sudo rm  -rf  trpc_a2a.egg-info
sudo rm  -rf dist/
sudo rm  -rf build/


sudo rm  -rf  test_tracemalloc*
sudo rm  -rf  test-ngtest-ut-trpc_a2a*
sudo rm  -rf  cov.tmp
sudo rm  -rf  examples/*.lock
sudo rm  -rf  examples/*.log

sudo rm  -rf  examples/.__py_trpc_frame.lock
sudo rm  -rf  examples/.__trpc.lock


find -type d | grep __pycache__ | xargs sudo rm  -r

find ./ -type f -name "*.log" -exec sudo rm {} \;


pip3 uninstall -r requirements.txt -y
pip3 uninstall trpc_redis -y
pip3 uninstall redis -y
