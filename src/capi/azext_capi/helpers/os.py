# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Helper functions for working with the environment, files, and other operating system features.
"""

import os
import yaml


def set_environment_variables(dic=None):
    """
    Sets the key and value items of a dictionary into environment variables.
    """
    if not dic:
        return
    for key, value in dic.items():
        if value:
            os.environ[key] = f"{value}"


def write_to_file(filename, file_input):
    """
    Writes file_input into file
    """
    descriptor = os.open(path=filename, flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode=0o600)
    with open(descriptor, "w", encoding="utf-8") as manifest_file:
        manifest_file.write(file_input)


def prep_kube_config():
    """Prepares kubeconfig file for safe use with the "az aks get-credentials" command."""
    if "KUBECONFIG" in os.environ:
        kubeconfig_path = os.environ["KUBECONFIG"].split(os.pathsep)[0]
    else:
        kubeconfig_path = os.path.join(os.path.expanduser('~'), '.kube', 'config')
    if os.path.exists(kubeconfig_path):
        with open(kubeconfig_path, "r+", encoding="utf-8") as file_pointer:
            config = yaml.safe_load(file_pointer)
            changed = False
            for key in ["clusters", "contexts", "users"]:
                if key not in config:
                    config[key] = []
                    changed = True
            if changed:
                file_pointer.seek(0)
                yaml.safe_dump(config, file_pointer)
                file_pointer.truncate()
