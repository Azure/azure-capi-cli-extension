#!/usr/bin/env bash
#-------------------------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See https://go.microsoft.com/fwlink/?linkid=2090316 for license information.
#-------------------------------------------------------------------------------------------------------------
#
# Create a python 3 virtual environment for developing this Azure CLI extension.
#
# Syntax: ./create-dev-env.sh
#

set -x

python3 -m venv env

# Activate the virtualenv automatically in GitHub Codespace shells
if [ "$CODESPACES" == "true" ]; then
    echo 'if [ -d "./env" ]; then source ./env/bin/activate; fi' >> ~/.bashrc
    echo 'if [ -d "./env" ]; then source ./env/bin/activate; fi' >> ~/.zshrc
fi

source ./env/bin/activate
pip install --upgrade pip
pip install azdev
azdev setup --repo . --ext capi --verbose
