# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains functions to help with command-line prompting via the [TAB] key.
"""

from azure.cli.core.decorators import Completer

# pylint: disable=import-outside-toplevel


@Completer
def get_kubernetes_version_completion_list(cmd, prefix, namespace, **kwargs):  # pylint: disable=unused-argument
    """Return a list of SKU versions for the CAPZ marketplace offer."""
    import re

    from azure.cli.command_modules.vm.custom import list_vm_images

    result = list_vm_images(cmd, publisher_name="cncf-upstream", offer="capi", all=True)
    regex = re.compile(r'k8s-(\d)dot(\d+)dot(\d+)-')

    def extract_version(sku):
        match = regex.match(sku)
        return ".".join(match.groups()) if match else ""

    return [extract_version(i['sku']) for i in result]


@Completer
def get_workflow_clusters_completion_list(cmd, prefix, namespace, **kwargs):  # pylint: disable=unused-argument
    """Return a list of the names of workload clusters."""
    from .custom import list_workload_clusters

    clusters = list_workload_clusters(cmd)
    return [i['metadata']['name'] for i in clusters.get('items', [])]


@Completer
def get_vm_size_completion_list(cmd, prefix, namespace, **kwargs):  # pylint: disable=unused-argument
    """Return available VM sizes."""
    from ._client_factory import cf_compute_service

    location = _get_location(cmd.cli_ctx, namespace)
    sizes = cf_compute_service(cmd.cli_ctx).virtual_machine_sizes.list(location)
    return [s.name for s in sizes]


def _get_location(cli_ctx, namespace):
    """
    Return an Azure location by using an explicit `--location` argument, then by `--resource-group`, and
    finally by the subscription if neither argument was provided.
    """
    from azure.cli.core.commands.parameters import get_one_of_subscription_locations

    location = None
    if getattr(namespace, 'location', None):
        location = namespace.location
    elif getattr(namespace, 'resource_group_name', None):
        location = _get_location_from_resource_group(cli_ctx, namespace.resource_group_name)
    if not location:
        location = get_one_of_subscription_locations(cli_ctx)
    return location


def _get_location_from_resource_group(cli_ctx, resource_group_name):
    from ._client_factory import cf_resource_groups
    from msrestazure.azure_exceptions import CloudError

    location = None
    try:
        resource_group = cf_resource_groups(cli_ctx).get(resource_group_name)
        location = resource_group.location
    except CloudError as err:
        # Print a warning if the user hit [TAB] but the `--resource-group` argument was incorrect.
        # For example: "Warning: Resource group 'bogus' could not be found."
        from argcomplete import warn
        warn(f'Warning: {err.message}')
    return location
