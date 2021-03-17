# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""This module loads the definitions of `az capi` commands.
"""

# pylint: disable=invalid-name

from ._format import CLUSTER_TABLE_FORMAT
from ._format import CLUSTERS_LIST_TABLE_FORMAT


def load_command_table(self, _):
    """Loads CAPI commands into the parser."""

    with self.command_group('capi', is_preview=True) as g:
        g.custom_command('create', 'create_workload_cluster')
        g.custom_command('delete', 'delete_workload_cluster')
        g.custom_command('list', 'list_workload_clusters',
                         table_transformer=CLUSTERS_LIST_TABLE_FORMAT)
        g.custom_command('show', 'show_workload_cluster',
                         table_transformer=CLUSTER_TABLE_FORMAT)
        g.custom_command('update', 'update_workload_cluster')

    with self.command_group('capi management', is_preview=True) as g:
        g.custom_command('create', 'create_management_cluster')
        g.custom_command('delete', 'delete_management_cluster')
        g.custom_command('move', 'move_management_cluster')
        g.custom_command('show', 'show_management_cluster')
        g.custom_command('update', 'update_management_cluster')
