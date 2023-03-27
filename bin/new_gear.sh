#!/bin/bash

echo "making new gear directories named '$1'"


mkdir -p $1/src/python
touch $1/src/python/main.py
touch $1/src/python/run.py

mkdir -p $1/test/python
touch $1/test/python/.gitkeep

mkdir -p $1/src/docker
touch $1/src/docker/Dockerfile
touch $1/src/docker/manifest.json

mkdir -p docs/$1
touch docs/$1/index.md
echo "# $1" > docs/$1/index.md
