# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains JMESPath queries to format output for the az capi extension.
"""


CLUSTER_TABLE_FORMAT = """\
{
    name: metadata.name,
    created: metadata.creationTimestamp,
    namespace: metadata.namespace
}
"""

CLUSTERS_LIST_TABLE_FORMAT = """\
items[].{
    name: metadata.name,
    created: metadata.creationTimestamp,
    namespace: metadata.namespace
}
"""
