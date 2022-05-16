# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains helper functions for the az capi extension.
"""


def add_kubeconfig_to_command(kubeconfig=None):
    return ["--kubeconfig", kubeconfig] if kubeconfig else []


def has_kind_prefix(inpt_str):
    return inpt_str.startswith("kind-")
