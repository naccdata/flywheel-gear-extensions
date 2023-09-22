FROM mcr.microsoft.com/devcontainers/python:3.10

ENV USERHOME=/home/vscode/bin
RUN mkdir -p ${USERHOME} \
 && export FW_CLI_INSTALL_DIR=${USERHOME} \
 && curl https://storage.googleapis.com/flywheel-dist/fw-cli/stable/install.sh | bash \
 && echo "alias fw='fw-beta'" > /etc/bash.bashrc \
 && chown -R vscode ${USERHOME}
