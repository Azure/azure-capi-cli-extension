# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains functions and JMESPath queries to format output for the az capi extension.

The knack CLI framework does not expect the JSON structures returned by `kubectl`. These
transformations expose useful fields for the table and tab-separated output formats.
"""

import json

import jmespath


CLUSTER_TABLE_FORMAT = """\
{
    name: metadata.name,
    phase: status.phase,
    created: metadata.creationTimestamp,
    namespace: metadata.namespace
}
"""

CLUSTERS_LIST_TABLE_FORMAT = f"items[].{CLUSTER_TABLE_FORMAT}"


def output_for_tsv(s):
    """Return JSON data to output a cluster in tab-separated format."""
    return jmespath.search(CLUSTER_TABLE_FORMAT, json.loads(s))


def output_list_for_tsv(s):
    """Return JSON data to output a list of clusters in tab-separated format."""
    return jmespath.search(CLUSTERS_LIST_TABLE_FORMAT, json.loads(s))
