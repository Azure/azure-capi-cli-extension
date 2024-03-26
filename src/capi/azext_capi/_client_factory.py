# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains Azure client factory functions.
"""

from azure.cli.core.commands.client_factory import get_mgmt_service_client
from azure.cli.core.profiles import ResourceType


def cf_compute_service(cli_ctx, *_):
    """Return an Azure compute client."""
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_COMPUTE)


def cf_resource_groups(cli_ctx, subscription_id=None):
    """Return an Azure resource groups client."""
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES,
                                   subscription_id=subscription_id).resource_groups
