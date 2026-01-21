USERHOME=/home/vscode
USERBIN=${USERHOME}/bin
bash get-pants.sh -d ${USERBIN}

export FW_CLI_INSTALL_DIR=${USERBIN}
curl https://storage.googleapis.com/flywheel-dist/fw-cli/stable/install.sh | bash

# Configure bash shell
cat > ${USERHOME}/.bashrc << 'EOF'
# Add user bin to PATH for Pants and other tools
export PATH="${HOME}/bin:${PATH}"

# Flywheel CLI alias
alias fw='fw-beta'
EOF

# Configure zsh shell (for interactive terminal.sh sessions)
cat > ${USERHOME}/.zshrc << 'EOF'
# Add user bin to PATH for Pants and other tools
export PATH="${HOME}/bin:${PATH}"

# Flywheel CLI alias
alias fw='fw-beta'

# Enable colors
autoload -U colors && colors

# Git branch in prompt
autoload -Uz vcs_info
precmd_vcs_info() { vcs_info }
precmd_functions+=( precmd_vcs_info )
setopt prompt_subst
zstyle ':vcs_info:git:*' formats ' (%b)'
zstyle ':vcs_info:*' enable git

# Prompt: username ➜ /path (branch) $
PROMPT='%{$fg[green]%}%n%{$reset_color%} ➜ %{$fg[cyan]%}%~%{$reset_color%}%{$fg[yellow]%}${vcs_info_msg_0_}%{$reset_color%} $ '
EOF

chown -R vscode ${USERBIN}
chown vscode:vscode ${USERHOME}/.bashrc ${USERHOME}/.zshrc

git config --global --add safe.directory $1
