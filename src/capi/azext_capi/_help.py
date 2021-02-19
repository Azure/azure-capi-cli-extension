# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains help string definitions for the `az capi` extension.
"""

from knack.help_files import helps  # pylint: disable=unused-import


helps['capi'] = """
    type: group
    short-summary: Manage Kubernetes clusters as declarative infrastructure using Cluster API.
    long-summary: |
        Cluster API brings declarative, Kubernetes-style APIs to cluster creation,
        configuration, and management. See https://capz.sigs.k8s.io/ for more info.
"""

helps['capi create'] = """
    type: command
    short-summary: Create a workload cluster.
    long-summary: |
        See https://capz.sigs.k8s.io/ for more information.
"""

helps['capi delete'] = """
    type: command
    short-summary: Delete a workload cluster.
    long-summary: |
        See https://capz.sigs.k8s.io/ for more information.
"""

helps['capi update'] = """
    type: command
    short-summary: Update a workload cluster.
    long-summary: |
        See https://capz.sigs.k8s.io/ for more information.
"""

helps['capi management'] = """
    type: group
    short-summary: Manage Cluster API management clusters.
    long-summary: |
        A CAPI management cluster manages the lifecycle of workload clusters.
        A management cluster is also where one or more infrastructure providers run,
        and where resources such as machines are stored.

        See https://capz.sigs.k8s.io/ for more information.
"""

helps['capi management create'] = """
    type: command
    short-summary: Create a CAPI management cluster.
"""

helps['capi management delete'] = """
    type: command
    short-summary: Delete a CAPI management cluster.
"""

helps['capi management move'] = """
    type: command
    short-summary: Move a CAPI management cluster.
"""

helps['capi management show'] = """
    type: command
    short-summary: Show details of a CAPI management cluster.
"""

helps['capi management update'] = """
    type: command
    short-summary: Update a CAPI management cluster.
"""
