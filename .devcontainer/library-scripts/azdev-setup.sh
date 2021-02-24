#!/usr/bin/env bash
#-------------------------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See https://go.microsoft.com/fwlink/?linkid=2090316 for license information.
#-------------------------------------------------------------------------------------------------------------
#
# Syntax: ./azdev-setup.sh

set -euo pipefail

PIPX_HOME=${1:-"/usr/local/py-utils"}

pipx install --system-site-packages azdev
ln -s /usr/local/bin/python ${PIPX_HOME}/bin
pip install flake8 pylint

echo 'alias azdev="VIRTUAL_ENV=${PIPX_HOME} azdev"' >> /etc/bash.bashrc
echo 'alias azdev="VIRTUAL_ENV=${PIPX_HOME} azdev"' >> /etc/zsh/zshrc
