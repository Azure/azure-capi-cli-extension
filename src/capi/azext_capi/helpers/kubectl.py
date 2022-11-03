# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains helper functions for the az capi extension.
"""

import subprocess
import os
import time
import re
import json

from azure.cli.core.azclierror import UnclassifiedUserFault
from azure.cli.core.azclierror import ResourceNotFoundError
from azure.cli.core.azclierror import InvalidArgumentValueError

from .run_command import run_shell_command
from .os import write_to_file
from .generic import match_output
from .logger import logger
from .constants import KUBECONFIG


def add_kubeconfig_to_command(kubeconfig=None):
    """Returns a list with kubeconfig flag"""
    return ["--kubeconfig", kubeconfig] if kubeconfig else []


def find_kubectl_current_context():
    """Returns kubectl current-context if exists"""
    command = ["kubectl", "config", "current-context"]
    output = None
    try:
        output = run_shell_command(command)
        output = output.strip()
    except subprocess.CalledProcessError as err:
        if "current-context is not set" not in err.stdout:
            raise
    return output


def find_attribute_in_context(context_name, attribute="cluster"):
    """Returns specified attribute of provided context"""
    command = ["kubectl", "config", "get-contexts", context_name, "--no-headers"]
    result = None
    try:
        output = run_shell_command(command)
        output = output.split()
        if attribute == "cluster":
            result = output[2]
        elif attribute == "user":
            result = output[3]
        elif attribute == "namespace":
            result = output[4]
    except subprocess.CalledProcessError:
        pass
    return result


def find_cluster_in_current_context():
    """Returns cluster name of current-context"""
    current_context = find_kubectl_current_context()
    cluster_name = None
    if current_context:
        cluster_name = find_attribute_in_context(current_context, "cluster")
        if not cluster_name:
            logger.error("No cluster in context %s", current_context)
    else:
        logger.error("No kubectl current-context found")
    if not cluster_name:
        logger.warning("Proceeding to create a new management cluster")
    return cluster_name


def merge_kubeconfig(kubeconfig):
    """Merges provided kubeconfig with default kubeconfig"""
    home = os.environ["HOME"]
    config_path = f"{home}/.kube/config"
    os.environ[KUBECONFIG] = f"{kubeconfig}:{config_path}"
    output = get_default_kubeconfig()
    filename = "config"
    with open(filename, "w", encoding="utf-8") as kubeconfig_file:
        kubeconfig_file.write(output)
    command = ["mv", filename, config_path]
    run_shell_command(command)


def get_default_kubeconfig():
    """Returns full default kubeconfig"""
    command = ["kubectl", "config", "view", "--flatten"]
    return run_shell_command(command)


def reset_current_context_and_attributes():
    """Unsets current-context and deletes context and its attributes"""
    current_context = find_kubectl_current_context()
    cluster_name = find_attribute_in_context(current_context, "cluster")
    user = find_attribute_in_context(current_context, "user")
    delete_kubeconfig_attribute(cluster_name, "cluster")
    delete_kubeconfig_attribute(user, "user")
    delete_kubeconfig_attribute(current_context, "context")
    unset_kubectl_current_context()


def delete_kubeconfig_attribute(name, attribute="context"):
    """Deletes attribute from default kubeconfig"""
    command = ["kubectl", "config", f"delete-{attribute}", name]
    run_shell_command(command)


def unset_kubectl_current_context():
    """Unsets current-context of default kubeconfig"""
    command = ["kubectl", "config", "unset", "current-context"]
    run_shell_command(command)


def find_kubectl_resource_names(resource_type, error_msg, kubeconfig=None):
    """Returns names of specified resource"""
    command = ["kubectl", "get", resource_type, "--output", "name"]
    command += add_kubeconfig_to_command(kubeconfig)
    try:
        return run_shell_command(command).splitlines()
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault(error_msg) from err


def get_kubeconfig(capi_name):
    """Writes kubeconfig of specified cluster"""
    cmd = ["clusterctl", "get", "kubeconfig", capi_name]
    try:
        output = run_shell_command(cmd, combine_std=False)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't get kubeconfig") from err
    filename = capi_name + ".kubeconfig"
    write_to_file(filename, output)
    return f"Wrote kubeconfig file to {filename} "


def check_kubectl_namespace(namespace):
    """Verifies that given namespace is active"""
    cmd = ["kubectl", "get", "namespaces", namespace]
    try:
        output = run_shell_command(cmd)
        match = match_output(output, fr"{namespace}.+?Active")
        if match is None:
            raise ResourceNotFoundError(f"namespace: {namespace} status is not Active")
    except subprocess.CalledProcessError as err:
        raise ResourceNotFoundError(f"namespace: {namespace} could not be found!") from err


def find_default_cluster():
    """Verifies that cluster has running status"""
    cmd = ["kubectl", "cluster-info"]
    output = run_shell_command(cmd)
    match = match_output(output, r"Kubernetes .*?is running")
    if match is None:
        raise ResourceNotFoundError("No accessible Kubernetes cluster found")
    return True


def find_nodes(kubeconfig):
    """Returns node names of specified cluster"""
    error_msg = "Couldn't get nodes of workload cluster"
    return find_kubectl_resource_names("nodes", error_msg, kubeconfig)


def wait_for_nodes(kubeconfig):
    """
    Waits for nodes of specified cluster to get be ready before proceeding.
    Timeout: 5 minutes
    """
    error_msg = "Not all cluster nodes are Ready after 5 minutes."
    wait_for_resource_ready(find_nodes, error_msg, kubeconfig)


def wait_for_number_of_nodes(number_of_nodes, kubeconfig=None):
    """
    Waits for nodes of specified cluster to get be ready before proceeding.
    Timeout: 5 minutes
    """
    error_msg = "Not all cluster nodes are Ready after 10 minutes."
    command = ["kubectl", "get", "nodes", "-o", "json"]
    command += add_kubeconfig_to_command(kubeconfig)
    timeout = 60 * 10
    start = time.time()
    while time.time() < start + timeout:
        try:
            kubectl_output = run_shell_command(command)
            json_output = json.loads(kubectl_output)
            ready_nodes = 0
            for item in json_output["items"]:
                for condition in item["status"]["conditions"]:
                    if condition["type"] == "Ready" and condition["status"] == "True":
                        ready_nodes += 1
            if ready_nodes < number_of_nodes:
                time.sleep(5)
                continue
            return
        except subprocess.CalledProcessError as err:
            logger.info(err)
            time.sleep(5)
    raise ResourceNotFoundError(error_msg)


def wait_for_resource_ready(find_resources, error_msg, kubeconfig=None,):
    """
    Runs wait command from kubectl and checks for readiness of specified resources.
    Timeout: 5 minutes
    """
    command = ["kubectl", "wait", "--for", "condition=Ready", "--timeout", "10s"]
    command += add_kubeconfig_to_command(kubeconfig)
    timeout = 60 * 5
    start = time.time()
    while time.time() < start + timeout:
        command += find_resources(kubeconfig)
        try:
            run_shell_command(command)
            return
        except subprocess.CalledProcessError as err:
            logger.info(err)
            time.sleep(5)
    raise ResourceNotFoundError(error_msg)


def wait_for_machines(kubeconfig=None):
    """
    Waits for machines of specified cluster to get be ready before proceeding.
    Timeout: 5 minutes
    """
    error_msg = "Not all machines are Ready after 5 minutes."
    wait_for_resource_ready(find_machines, error_msg, kubeconfig)


def find_machines(kubeconfig=None):
    """Returns machines names of specified cluster"""
    error_msg = "Couldn't get machines of cluster"
    return find_kubectl_resource_names("machines", error_msg, kubeconfig)


def check_pods_status_by_namespace(namespace, error_message, pod_name):
    """Verifies that pod's status is running"""
    get_pods_cmd = ["kubectl", "get", "pods"]
    cmd = get_pods_cmd + ["--namespace", namespace]
    try:
        output = run_shell_command(cmd)
        match = match_output(output, fr"No resources found in {namespace} namespace")
        if match:
            raise ResourceNotFoundError(error_message)
        match = match_output(output, fr"{pod_name}-.+?Running")
        if match is None:
            raise ResourceNotFoundError(f"No pods running in {namespace} namespace")
    except subprocess.CalledProcessError as err:
        cmd = get_pods_cmd + ["-A", namespace]
        try:
            output = run_shell_command(cmd)
            logger.debug(output)
        except subprocess.CalledProcessError as err:
            logger.error(err)
        logger.error(err)
        raise


def get_azure_cluster(cluster_name, kubeconfig=None):
    """Returns AzureCluster Object"""
    command = ["kubectl", "get", "AzureCluster", cluster_name, "-o", "json"]
    command += add_kubeconfig_to_command(kubeconfig)
    try:
        return run_shell_command(command)
    except subprocess.CalledProcessError as err:
        raise InvalidArgumentValueError(f"Could not find {cluster_name}") from err


def get_kubectl_cluster_info(kubeconfig=None):
    """Returns kubectl cluster-info result"""
    command = ["kubectl", "cluster-info"]
    command += add_kubeconfig_to_command(kubeconfig)
    return run_shell_command(command)


def get_ports_cluster(kubeconfig=None):
    """Returns dictionary with cluster component ports"""
    output = get_kubectl_cluster_info(kubeconfig)
    match = re.findall(r"(?<=is running at )[^\s]{1,}", output)
    result = {
        "control_plane": match[0],
        "coredns": match[1]
    }
    return result
