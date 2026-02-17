# Dev Container Workflow

This project uses dev containers for consistent development environments. When executing commands, use the devcontainer scripts in the `bin/` directory.

## Running Commands in the Dev Container

**IMPORTANT**: All Pants commands and setup scripts should be executed inside the running dev container, not on the host machine.

**CRITICAL**: Before executing any commands in the container, ALWAYS check if the container is running first by running `./bin/start-devcontainer.sh`. This command is idempotent - it will start the container if stopped, or do nothing if already running.

### Commands to Run in Container

Use `./bin/exec-in-devcontainer.sh` to execute these commands:

#### Setup
```bash
./bin/exec-in-devcontainer.sh bash get-pants.sh
```

#### Code Quality
```bash
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
```

#### Testing
```bash
./bin/exec-in-devcontainer.sh pants test ::
./bin/exec-in-devcontainer.sh pants test common/test/python::
./bin/exec-in-devcontainer.sh pants test path/to/test_file.py
```

#### Running Scripts
```bash
./bin/exec-in-devcontainer.sh pants run scripts/example_script/src/python:main
```

### Interactive Shell

For multiple commands or interactive work, open a shell in the container:

```bash
./bin/terminal.sh
```

Then run commands directly:
```bash
pants fix ::
pants lint ::
pants test ::
```

## Container Management

### Start Container
```bash
./bin/start-devcontainer.sh
```

### Stop Container
```bash
./bin/stop-devcontainer.sh
```

### Rebuild Container
After changing `.devcontainer/` configuration:
```bash
./bin/build-container.sh
./bin/start-devcontainer.sh
```

## Python Environment

The dev container provides Python 3.12 pre-installed. No need for pyenv or manual Python installation - the container handles this.

## Workflow Example

```bash
# Always start/ensure container is running first
./bin/start-devcontainer.sh

# Run commands in the container
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
./bin/exec-in-devcontainer.sh pants test ::

# Or open an interactive shell
./bin/terminal.sh

# Stop when done
./bin/stop-devcontainer.sh
```

## Kiro AI Assistant Workflow

When executing commands as Kiro:

1. **ALWAYS** run `./bin/start-devcontainer.sh` first to ensure the container is running
2. Then execute the desired command with `./bin/exec-in-devcontainer.sh`
3. The start command is safe to run multiple times - it won't restart a running container
