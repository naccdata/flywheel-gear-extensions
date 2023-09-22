USERHOME=/home/vscode
USERBIN=${USERHOME}/bin
bash bin/get-pants.sh -d ${USERBIN}

export FW_CLI_INSTALL_DIR=${USERBIN}
curl https://storage.googleapis.com/flywheel-dist/fw-cli/stable/install.sh | bash
echo "alias fw='fw-beta'" > ${USERHOME}/.bashrc
chown -R vscode ${USERBIN}


# git config --global --add safe.directory $1
