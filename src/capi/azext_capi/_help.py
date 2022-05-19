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
short-summary: Create a workload cluster
long-summary: |
  See https://capz.sigs.k8s.io/ for more information
parameters:
  - name: --control-plane-machine-count
    type: integer
  - name: --control-plane-machine-type
    type: string
  - name: --ephemeral-disks -e
    type: string
    short-summary: Use ephemeral disks
  - name: --external-cloud-provider
    type: bool
  - name: --kubernetes-version -k
    type: string
    short-summary: Version of Kubernetes to use
    populator-commands:
      - "`az vm image list -p cncf-upstream -f capi --all`"
  - name: --location -l
    type: string
    long-summary: |
        If not specified, the location of the --resource-group will be used.
        Required if --resource-group is not specified or does not yet exist
  - name: --machinepool
    type: bool
    short-summary: Use experimental MachinePools instead of MachineSets
  - name: --management-cluster-name
    type: string
    short-summary: Name for management cluster.
  - name: --node-machine-count
    type: integer
  - name: --node-machine-type
    type: string
  - name: --output-path -p
    type: string
    short-summary: Where to save helper commands when they are downloaded
  - name: --pivot
    type: bool
    short-summary: Move provider and CAPI resources to workload cluster.
    long-summary: |
       Learn more about pivot at https://cluster-api.sigs.k8s.io/clusterctl/commands/move.html
  - name: --resource-group -g
    type: string
    long-summary: |
        If not specified, the value of --name will be used
  - name: --vnet-name
    type: string
    short-summary: Name of the Virtual Network to create
  - name: --windows -w
    type: bool
    short-summary: Include a Windows node pool
"""

helps['capi delete'] = """
type: command
short-summary: Delete a workload cluster.
long-summary: |
    See https://capz.sigs.k8s.io/ for more information.
"""

helps['capi install'] = """
type: command
short-summary: installs all needed tools
parameters:
  - name: --all -a
    type: bool
"""

helps['capi show'] = """
type: command
short-summary: Show details of a workload cluster.
long-summary: |
    See https://capz.sigs.k8s.io/ for more information.
"""

helps['capi list'] = """
type: command
short-summary: List workload clusters.
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
parameters:
  - name: --cluster-name
    type: string
    short-summary: Name for management cluster.
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
