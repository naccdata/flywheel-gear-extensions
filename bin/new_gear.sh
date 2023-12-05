#!/bin/bash

echo "making new gear directories named '$1'"

project=$1
prefix="${project%%_*}"
export DIRNAME=$1
export IMAGENAME=`echo $1 | tr '_' '-'`
export IMAGETAG="0.0.1"
export APPNAME="${prefix}_app"
export FILEKEY="${prefix}_file"
export MAINFILE="${prefix}_main"


mkdir -p gear/$1/src/python/${APPNAME}
cat templates/python/build-template.txt | envsubst > "gear/$1/src/python/${APPNAME}/BUILD"
cat templates/python/run-template.txt | envsubst > "gear/$1/src/python/${APPNAME}/run.py"
cat templates/python/main-template.txt | envsubst > "gear/$1/src/python/${APPNAME}/main.py"
touch "gear/$1/src/python/${APPNAME}/__init__.py"

mkdir -p gear/$1/test/python
touch gear/$1/test/python/.gitkeep

mkdir -p gear/$1/src/docker
cat templates/docker/build-template.txt | envsubst > gear/$1/src/docker/BUILD
cat templates/docker/dockerfile-template.txt | envsubst '${DIRNAME}' > gear/$1/src/docker/Dockerfile
cat templates/docker/manifest-template.txt | envsubst > gear/$1/src/docker/manifest.json
cat templates/docker/gitignore-template.txt > gear/$1/src/docker/.gitignore

mkdir -p docs/$1
touch docs/$1/index.md
echo "# $1" > docs/$1/index.md
