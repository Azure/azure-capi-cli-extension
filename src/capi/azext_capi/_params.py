# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module defines the parameters (aka arguments) for `az capi` commands.
"""

import os
import os.path
import platform

from knack.arguments import CLIArgumentType

from ._completers import get_kubernetes_version_completion_list
from ._completers import get_vm_size_completion_list
from ._completers import get_workflow_clusters_completion_list


def load_arguments(self, _):
    """Loads command arguments into the parser."""

    capi_name_type = CLIArgumentType(
        options_list='--capi-name-name', help='Name of the CAPI Kubernetes cluster.')

    with self.argument_context('capi') as ctx:
        ctx.argument('capi_name', capi_name_type, options_list=['--name', '-n'],
                     completer=get_workflow_clusters_completion_list)
        ctx.argument('control_plane_machine_count', options_list=['--control-plane-machine-count', '-u'])
        ctx.argument('control_plane_machine_type', options_list=['--control-plane-machine-type', '-z'],
                     completer=get_vm_size_completion_list)
        ctx.argument('ephemeral_disks', options_list=['--ephemeral-disks', '-e'])
        ctx.argument('kubernetes_version', options_list=['--kubernetes-version', '-k'],
                     completer=get_kubernetes_version_completion_list)
        ctx.argument('machinepool', options_list=['--machinepool', '-m'])
        ctx.argument('management_cluster_name', options_list=['--management-cluster-name', '-j'])
        ctx.argument('management_cluster_resource_group_name',
                     options_list=['--management-cluster-resource-group-name', '-q'])
        ctx.argument('node_machine_type', completer=get_vm_size_completion_list)
        ctx.argument('tags', options_list=['--tags', '-t'])
        ctx.argument('user_provided_template', options_list=['--template'])
        ctx.argument('vnet_name', options_list=['--vnet-name'])
        ctx.argument('wait_for_nodes', options_list=['--wait-for-nodes'])
        ctx.argument('windows', options_list=['--windows', '-w'])
        ctx.argument('yes', options_list=['--yes', '-y'], help="Do not prompt for confirmation")

    with self.argument_context('capi create') as ctx:
        ctx.argument('external_cloud_provider', options_list=['--external-cloud-provider', '-x'])

    with self.argument_context('capi install') as ctx:
        ctx.argument('all_tools', options_list=['--all', '-a'])
        ctx.argument('install_path', options_list=['--install-path', '-p'])


def get_virtualenv():
    return os.getenv("VIRTUAL_ENV")


def _get_default_install_location(exe_name):
    install_location = None
    system = platform.system()
    if system == 'Windows':
        home_dir = os.environ.get('USERPROFILE')
        if not home_dir:
            return None
        install_location = os.path.join(
            home_dir, fr'.azure-{exe_name}\{exe_name}.exe')
    elif system in ('Linux', 'Darwin'):
        venv = get_virtualenv()
        if venv:
            install_location = f'{venv}/bin/{exe_name}'
        else:
            install_location = f'/usr/local/bin/{exe_name}'
    return install_location
