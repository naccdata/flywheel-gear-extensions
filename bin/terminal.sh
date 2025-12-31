#!/bin/zsh

if ! command -v devcontainer &> /dev/null; then
    echo "Error: devcontainer command not found"
    echo "Please install the devcontainer CLI: npm install -g @devcontainers/cli"
    exit 1
fi

export WORKSPACE_FOLDER=`pwd`
export DOCKER_CLI_HINTS=false
export CONTAINER_HOST=`devcontainer exec --workspace-folder $WORKSPACE_FOLDER hostname`
export WORKSPACE=`basename $WORKSPACE_FOLDER`
docker exec -u vscode -w /workspaces/$WORKSPACE -ti $CONTAINER_HOST /bin/zsh
