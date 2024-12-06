#!/bin/sh
# Sets up a gear for a local run

set -euo pipefail

GEAR=$1
FW_API_KEY=$2
FW_PATH=${3:-nacc/project-admin}
FW_CONTEXT=${4:-sandbox}  # sandbox or prod

config_dir="./gear/${GEAR}/src/docker"

echo "Setting up config for $GEAR at $config_dir"

#######################
# Basic configuration #
#######################

# Set up config using defaults from manifest
fw-beta gear config --new $config_dir

# Set API key
fw-beta gear config -i api_key=$FW_API_KEY $config_dir

# Set destination for output
fw-beta gear config -d $FW_PATH $config_dir

# Set the apikey_path_prefix to specified fw context (sandbox or prod)
fw-beta gear config -i api_key="/${FW_CONTEXT}/flywheel/gearbot" $config_dir
