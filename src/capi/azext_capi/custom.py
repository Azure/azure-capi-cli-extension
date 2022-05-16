# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""This module implements the behavior of `az capi` commands."""

# pylint: disable=missing-docstring

import base64
import json
import os
import re
import subprocess
import time

from azure.cli.core import get_default_cli
from azure.cli.core.api import get_config_dir
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import RequiredArgumentMissingError
from azure.core.exceptions import ResourceNotFoundError as ResourceNotFoundException
from azure.cli.core.azclierror import ResourceNotFoundError
from azure.cli.core.azclierror import UnclassifiedUserFault
from jinja2 import Environment, PackageLoader, StrictUndefined
from jinja2.exceptions import UndefinedError
from knack.prompting import prompt_choice_list, prompt_y_n
from knack.prompting import prompt as prompt_method
from msrestazure.azure_exceptions import CloudError

from .helpers.generic import add_kubeconfig_to_command, has_kind_prefix
from .helpers.logger import is_verbose, logger
from .helpers.spinner import Spinner
from .helpers.run_command import try_command_with_spinner, run_shell_command
from .helpers.binary import check_clusterctl, check_kubectl, check_kind

MANAGEMENT_RG_NAME = "MANAGEMENT_RG_NAME"
KUBECONFIG = "KUBECONFIG"


def init_environment(cmd, prompt=True, management_cluster_name=None,
                     resource_group_name=None, location=None):
    check_prereqs(cmd, install=True)
    # Create a management cluster if needed
    use_new_cluster = False
    pre_prompt = None
    try:
        find_management_cluster_retry(cmd)
        cluster_name = find_cluster_in_current_context()
        if prompt and not prompt_y_n(f"Do you want to use {cluster_name} as the management cluster?"):
            use_new_cluster = True
        else:
            return True
    except ResourceNotFoundError as err:
        error_msg = err.error_msg
        if management_cluster_components_missing_matching_expressions(error_msg):
            choices = ["Create a new management cluster",
                       "Use default kuberenetes cluster found and install CAPI required components",
                       "Exit"]
            msg = "The default kubernetes cluster found is missing required components for a management cluster.\
                   \nDo you want to:"

            index_choice = 0
            if prompt:
                index_choice = prompt_choice_list(msg, choices)
            if index_choice == 0:
                use_new_cluster = True
            elif index_choice != 1:
                return False
        else:
            raise UnclassifiedUserFault(err) from err
    except subprocess.CalledProcessError:
        pre_prompt = """
No Kubernetes cluster was found using the default configuration.

Cluster API needs a "management cluster" to run its components.
Learn more from the Cluster API Book:
https://cluster-api.sigs.k8s.io/user/concepts.html
"""
        use_new_cluster = True
    if use_new_cluster and not create_new_management_cluster(cmd, management_cluster_name,
                                                             resource_group_name, location,
                                                             pre_prompt_text=pre_prompt, prompt=prompt):
        return False

    _create_azure_identity_secret(cmd)
    _install_capi_provider_components(cmd)
    return True


def _create_azure_identity_secret(cmd, kubeconfig=None):
    secret_name = os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAME"]
    secret_namespace = os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"]
    azure_client_secret = os.environ["AZURE_CLIENT_SECRET"]
    begin_msg = "Creating Cluster Identity Secret"
    end_msg = "✓ Created Cluster Identity Secret"
    error_msg = "Can't create Cluster Identity Secret"
    command = ["kubectl", "create", "secret", "generic", secret_name, "--from-literal",
               f"clientSecret={azure_client_secret}", "--namespace", secret_namespace]
    command += add_kubeconfig_to_command(kubeconfig)
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg, True)


def _install_capi_provider_components(cmd, kubeconfig=None):
    os.environ["EXP_MACHINE_POOL"] = "true"
    os.environ["EXP_CLUSTER_RESOURCE_SET"] = "true"
    begin_msg = "Initializing management cluster"
    end_msg = "✓ Initialized management cluster"
    error_msg = "Couldn't install CAPI provider components in current cluster"
    command = ["clusterctl", "init", "--infrastructure", "azure"]
    command += add_kubeconfig_to_command(kubeconfig)
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg)


def find_kubectl_current_context():
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


def create_resource_group(cmd, rg_name, location, yes=False):
    msg = f'Create the Azure resource group "{rg_name}" in location "{location}"?'
    if yes or prompt_y_n(msg, default="n"):
        command = ["az", "group", "create", "-l", location, "-n", rg_name]
        begin_msg = f"Creating Resource Group: {rg_name}"
        end_msg = f"✓ Created Resource Group: {rg_name}"
        err_msg = f"Could not create resource group {rg_name}"
        try_command_with_spinner(cmd, command, begin_msg, end_msg, err_msg)
        return True
    return False


def create_management_cluster(cmd, cluster_name=None, resource_group_name=None, location=None,
                              yes=False):
    check_prereqs(cmd)
    existing_cluster = find_cluster_in_current_context()
    found_cluster = False
    if existing_cluster:
        msg = f'Do you want to initialize Cluster API on the current cluster {existing_cluster}?'
        if yes or prompt_y_n(msg, default="n"):
            try:
                _find_default_cluster()
                found_cluster = True
            except subprocess.CalledProcessError as err:
                raise UnclassifiedUserFault("Can't locate a Kubernetes cluster") from err
    if not found_cluster and not create_new_management_cluster(cmd, cluster_name, resource_group_name,
                                                               location, prompt=not yes):
        return
    set_azure_identity_secret_env_vars()
    _create_azure_identity_secret(cmd)
    _install_capi_provider_components(cmd)


def get_cluster_name_by_user_prompt(default_name):
    prompt = "Please name the management cluster"
    regex_validator = "^[a-z0-9.-]+$"
    invalid_msg = "Invalid name for cluster: only lowercase characters, numbers, dashes and periods allowed"
    return get_user_prompt_or_default(prompt, default_name, regex_validator, invalid_msg)


def get_user_prompt_or_default(prompt_text, default_value, match_expression=None,
                               invalid_prompt=None, skip_prompt=False):

    if skip_prompt:
        return default_value

    prompt = f"{prompt_text} [Default {default_value}]: "
    while True:
        user_input = prompt_method(prompt)
        user_input = user_input.strip()
        if user_input == "":
            return default_value
        if match_expression and re.match(match_expression, user_input):
            return user_input
        if not match_expression:
            return user_input
        if invalid_prompt:
            logger.error(invalid_prompt)


def create_aks_management_cluster(cmd, cluster_name, resource_group_name=None, location=None, yes=False):
    if not resource_group_name:
        msg = "Please name the resource group for the management cluster"
        resource_group_name = get_user_prompt_or_default(msg, cluster_name, skip_prompt=yes)
    if not location:
        default_location = "southcentralus"
        msg = f"Please provide a location for {resource_group_name} resource group"
        location = get_user_prompt_or_default(msg, default_location, skip_prompt=yes)
    if not create_resource_group(cmd, resource_group_name, location, yes):
        return False
    command = ["az", "aks", "create", "-g", resource_group_name, "--name", cluster_name, "--generate-ssh-keys",
               "--network-plugin", "azure", "--network-policy", "calico"]
    try_command_with_spinner(cmd, command, "Creating Azure management cluster with AKS",
                             "✓ Created AKS management cluster", "Couldn't create AKS management cluster")
    os.environ[MANAGEMENT_RG_NAME] = resource_group_name
    with Spinner(cmd, "Obtaining AKS credentials", "✓ Obtained AKS credentials"):
        command = ["az", "aks", "get-credentials", "-g", resource_group_name, "--name", cluster_name]
        try:
            subprocess.check_call(command, universal_newlines=True)
        except subprocess.CalledProcessError as err:
            raise UnclassifiedUserFault("Couldn't get credentials for AKS management cluster") from err
    return True


def create_new_management_cluster(cmd, cluster_name=None, resource_group_name=None,
                                  location=None, pre_prompt_text=None, prompt=True):
    choices = ["azure - a management cluster in the Azure cloud",
               "local - a local Docker container-based management cluster",
               "exit - don't create a management cluster"]
    default_cluster_name = "capi-manager"
    if prompt:
        prompt_text = pre_prompt_text if pre_prompt_text else ""
        prompt_text += """
Where do you want to create a management cluster?
"""
        choice_index = prompt_choice_list(prompt_text, choices)
        if choice_index != 2 and not cluster_name:
            cluster_name = get_cluster_name_by_user_prompt(default_cluster_name)
    else:
        if not cluster_name:
            cluster_name = default_cluster_name
        choice_index = 0
    if choice_index == 0:
        if not create_aks_management_cluster(cmd, cluster_name, resource_group_name,
                                             location, yes=not prompt):
            return False
    elif choice_index == 1:
        check_kind(cmd, install=not prompt)
        begin_msg = f'Creating local management cluster "{cluster_name}" with kind'
        end_msg = f'✓ Created local management cluster "{cluster_name}"'
        command = ["kind", "create", "cluster", "--name", cluster_name]
        try_command_with_spinner(cmd, command, begin_msg, end_msg, "Couldn't create kind management cluster")
    else:
        return False
    return True


def delete_management_cluster(cmd, yes=False):  # pylint: disable=unused-argument
    exit_if_no_management_cluster()
    msg = 'Do you want to delete Cluster API components from the current cluster?'
    if not yes and not prompt_y_n(msg, default="n"):
        return

    command = ["clusterctl", "delete", "--all",
               "--include-crd", "--include-namespace"]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't delete components from management cluster") from err
    namespaces = [
        "capi-kubeadm-bootstrap-system",
        "capi-kubeadm-control-plane-system",
        "capi-system",
        "capz-system",
        "cert-manager",
    ]
    command = ["kubectl", "delete", "namespace", "--ignore-not-found"] + namespaces
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't delete namespaces from management cluster") from err


def move_management_cluster(cmd):
    raise NotImplementedError


def show_management_cluster(_cmd, yes=False):
    # TODO: check to see if a management cluster is specified in the config
    config = get_default_cli().config
    # Config can also be set by the AZURE_CAPI_KUBECONFIG environment variable.
    kubeconfig = config.get("capi", "kubeconfig",
                            fallback=os.environ.get("KUBECONFIG"))
    if not kubeconfig:
        raise InvalidArgumentValueError("no kubeconfig")
    # make a $HOME/.azure/capi directory for storing cluster configurations
    path = os.path.join(get_config_dir(), "capi")
    if not os.path.exists(path):
        os.makedirs(path)
    command = ["kubectl", "config", "get-contexts",
               "--no-headers", "--output", "name"]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
        contexts = output.splitlines()
        logger.info(contexts)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault from err

    msg = path + "ok"
    if not yes and prompt_y_n(msg, default="n"):
        logger.info("yes")
    # TODO: echo details of the management cluster in all output formats


def update_management_cluster(cmd, yes=False):
    exit_if_no_management_cluster()
    msg = 'Do you want to update Cluster API components on the current cluster?'
    if not yes and not prompt_y_n(msg, default="n"):
        return
    # Check for clusterctl tool
    check_prereqs(cmd, install=yes)
    command = [
        "clusterctl",
        "upgrade",
        "apply",
        "--management-group",
        "capi-system/cluster-api",
        "--contract",
        "v1alpha3",
    ]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't upgrade management cluster") from err


def set_azure_identity_secret_env_vars():
    identity_secret_name = "AZURE_CLUSTER_IDENTITY_SECRET_NAME"
    indentity_secret_namespace = "AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"
    cluster_identity_name = "CLUSTER_IDENTITY_NAME"
    os.environ[identity_secret_name] = os.environ.get(identity_secret_name, "cluster-identity-secret")
    os.environ[indentity_secret_namespace] = os.environ.get(indentity_secret_namespace, "default")
    os.environ[cluster_identity_name] = os.environ.get(cluster_identity_name, "cluster-identity")


# pylint: disable=inconsistent-return-statements
def create_workload_cluster(  # pylint: disable=unused-argument,too-many-arguments,too-many-locals,too-many-statements
        cmd,
        capi_name,
        resource_group_name=None,
        location=None,
        control_plane_machine_type=os.environ.get("AZURE_CONTROL_PLANE_MACHINE_TYPE", "Standard_D2s_v3"),
        control_plane_machine_count=os.environ.get("AZURE_CONTROL_PLANE_MACHINE_COUNT", 3),
        node_machine_type=os.environ.get("AZURE_NODE_MACHINE_TYPE", "Standard_D2s_v3"),
        node_machine_count=os.environ.get("AZURE_NODE_MACHINE_COUNT", 3),
        kubernetes_version=os.environ.get("AZURE_KUBERNETES_VERSION", "1.22.8"),
        subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID"),
        ssh_public_key=os.environ.get("AZURE_SSH_PUBLIC_KEY_B64", ""),
        external_cloud_provider=False,
        management_cluster_name=None,
        management_cluster_resource_group_name=None,
        vnet_name=None,
        machinepool=False,
        ephemeral_disks=False,
        windows=False,
        pivot=False,
        output_path=None,
        yes=False):

    # Check if the RG already exists and that it's consistent with the location
    # specified. CAPZ will actually create (and delete) the RG if needed.
    from ._client_factory import cf_resource_groups  # pylint: disable=import-outside-toplevel

    rg_client = cf_resource_groups(cmd.cli_ctx)
    if not resource_group_name:
        resource_group_name = capi_name
    try:
        rg = rg_client.get(resource_group_name)
        if not location:
            location = rg.location
        elif location != rg.location:
            msg = "--location is {}, but the resource group {} already exists in {}."
            raise InvalidArgumentValueError(msg.format(location, resource_group_name, rg.location))
    except (CloudError, ResourceNotFoundException) as err:
        if 'could not be found' not in err.message:
            raise
        if not location:
            msg = "--location is required to create the resource group {}."
            raise RequiredArgumentMissingError(msg.format(resource_group_name)) from err
        logger.warning("Could not find an Azure resource group, CAPZ will create one for you")

    msg = f'Create the Kubernetes cluster "{capi_name}" in the Azure resource group "{resource_group_name}"?'
    if not yes and not prompt_y_n(msg, default="n"):
        return

    # Set Azure Identity Secret enviroment variables. This will be used in init_environment
    set_azure_identity_secret_env_vars()

    if not init_environment(cmd, not yes, management_cluster_name, management_cluster_resource_group_name,
                            location):
        return

    # Generate the cluster configuration
    env = Environment(loader=PackageLoader("azext_capi", "templates"), auto_reload=False, undefined=StrictUndefined)
    logger.debug("Available templates: %s", env.list_templates())
    template = env.get_template("base.jinja")

    args = {
        "AZURE_CONTROL_PLANE_MACHINE_TYPE": control_plane_machine_type,
        "AZURE_LOCATION": location,
        "AZURE_NODE_MACHINE_TYPE": node_machine_type,
        "AZURE_RESOURCE_GROUP": resource_group_name,
        "AZURE_SUBSCRIPTION_ID": subscription_id,
        "AZURE_SSH_PUBLIC_KEY_B64": ssh_public_key,
        "AZURE_VNET_NAME": vnet_name,
        "CLUSTER_NAME": capi_name,
        "CONTROL_PLANE_MACHINE_COUNT": control_plane_machine_count,
        "EXTERNAL_CLOUD_PROVIDER": external_cloud_provider,
        "KUBERNETES_VERSION": kubernetes_version,
        "EPHEMERAL": ephemeral_disks,
        "WINDOWS": windows,
        "WORKER_MACHINE_COUNT": node_machine_count,
        "NODEPOOL_TYPE": "machinepool" if machinepool else "machinedeployment",
        "CLUSTER_IDENTITY_NAME": os.environ["CLUSTER_IDENTITY_NAME"],
        "AZURE_TENANT_ID": os.environ["AZURE_TENANT_ID"],
        "AZURE_CLIENT_ID": os.environ["AZURE_CLIENT_ID"],
        "AZURE_CLUSTER_IDENTITY_SECRET_NAME": os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAME"],
        "AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE": os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"],
    }

    filename = capi_name + ".yaml"
    end_msg = f'✓ Generated workload cluster configuration at "{filename}"'
    with Spinner(cmd, "Generating workload cluster configuration", end_msg):
        try:
            manifest = template.render(args)
            with open(filename, "w", encoding="utf-8") as manifest_file:
                manifest_file.write(manifest)
        except UndefinedError as err:
            raise RequiredArgumentMissingError(f"Could not generate workload cluster configuration. {err}") from err

    # Apply the cluster configuration.
    attempts, delay = 100, 3
    begin_msg = f'Creating workload cluster "{capi_name}"'
    end_msg = f'✓ Created workload cluster "{capi_name}"'
    with Spinner(cmd, begin_msg, end_msg):
        command = ["kubectl", "apply", "-f", filename]
        # if --verbose, don't capture stderr
        stderr = None if is_verbose() else subprocess.STDOUT
        for _ in range(attempts):
            try:
                output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
                logger.info("%s returned:\n%s", " ".join(command), output)
                break
            except subprocess.CalledProcessError as err:
                logger.info(err)
                time.sleep(delay)
        else:
            msg = "Couldn't apply workload cluster manifest after waiting 5 minutes."
            raise ResourceNotFoundError(msg)

    # Write the kubeconfig for the workload cluster to a file.
    # Retry this operation several times, then give up and just print the command.
    attempts, delay = 100, 3
    with Spinner(cmd, "Waiting for access to workload cluster", "✓ Workload cluster is accessible"):
        for _ in range(attempts):
            try:
                get_kubeconfig(capi_name)
                break
            except UnclassifiedUserFault:
                time.sleep(delay)
        else:
            msg = f"""\
Kubeconfig wasn't available after waiting 5 minutes.
When the cluster is ready, run this command to fetch the kubeconfig:
clusterctl get kubeconfig {capi_name}
"""
            raise ResourceNotFoundError(msg)

    workload_cfg = capi_name + ".kubeconfig"
    logger.warning('✓ Workload access configuration written to "%s"', workload_cfg)

    # Install CNI
    calico_manifest = "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api-provider-azure/master/templates/addons/calico.yaml"  # pylint: disable=line-too-long
    spinner_enter_message = "Deploying Container Network Interface (CNI) support"
    spinner_exit_message = "✓ Deployed CNI to workload cluster"
    error_message = "Couldn't install CNI after waiting 5 minutes."

    apply_calico_manifest(cmd, calico_manifest, workload_cfg, spinner_enter_message,
                          spinner_exit_message, error_message)

    if windows:
        calico_manifest = "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api-provider-azure/main/templates/addons/windows/calico/calico.yaml"  # pylint: disable=line-too-long
        spinner_enter_message = "Deploying Windows Calico support"
        spinner_exit_message = "✓ Deployed Windows Calico support to worload cluster"
        error_message = "Couldn't install Windows Calico support after waiting 5 minutes."
        apply_calico_manifest(cmd, calico_manifest, workload_cfg, spinner_enter_message,
                              spinner_exit_message, error_message)

    # Wait for all nodes to be ready before returning
    with Spinner(cmd, "Waiting for workload cluster nodes to be ready", "✓ Workload cluster is ready"):
        wait_for_nodes(workload_cfg)

    if pivot:
        pivot_cluster(cmd, workload_cfg)
    return show_workload_cluster(cmd, capi_name)


def pivot_cluster(cmd, target_cluster_kubeconfig):

    logger.warning("Starting Pivot Process")

    begin_msg = "Installing Cluster API components in target management cluster"
    end_msg = "✓ Installed Cluster API components in target management cluster"
    with Spinner(cmd, begin_msg, end_msg):
        set_azure_identity_secret_env_vars()
        _create_azure_identity_secret(cmd, target_cluster_kubeconfig)
        _install_capi_provider_components(cmd, target_cluster_kubeconfig)

    with Spinner(cmd, "Waiting for workload cluster machines to be ready", "✓ Workload cluster machines are ready"):
        wait_for_machines()

    command = ["clusterctl", "move", "--to-kubeconfig", target_cluster_kubeconfig]
    begin_msg = "Moving cluster objects into target cluster"
    end_msg = "✓ Moved cluster objects into target cluster"
    error_msg = "Could not complete clusterctl move action"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg, True)

    cluster_name = find_cluster_in_current_context()
    if has_kind_prefix(cluster_name):
        delete_kind_cluster_from_current_context(cmd)
    else:
        resource_group = os.environ.get(MANAGEMENT_RG_NAME, None)
        if not resource_group:
            raise UnclassifiedUserFault("Could not delete AKS management cluster, resource group missing")
        delete_aks_cluster(cmd, cluster_name, resource_group)

    # Merge workload cluster kubeconfig and default kubeconfig.
    # To preverse any previous existing contexts
    merge_kubeconfig(target_cluster_kubeconfig)
    logger.warning("Completed Pivot Process")
    return True


def merge_kubeconfig(kubeconfig):
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
    command = ["kubectl", "config", "view", "--flatten"]
    return run_shell_command(command)


def delete_kind_cluster(cmd, name):
    command = ["kind", "delete", "cluster", "--name", name]
    begin_msg = f"Deleting {name} kind cluster"
    end_msg = f"✓ Deleted {name} kind cluster"
    error_msg = "Could not delete kind cluster"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg)


def delete_kind_cluster_from_current_context(cmd):
    cluster_name = find_cluster_in_current_context()
    # remove prefix
    if has_kind_prefix(cluster_name):
        cluster_name = cluster_name[5:]
    delete_kind_cluster(cmd, cluster_name)


def delete_aks_cluster(cmd, name, resource_group):
    command = ["az", "aks", "delete", "--name", name, "--resource-group", resource_group, "--yes"]
    begin_msg = f"Deleting {name} AKS cluster"
    end_msg = f"✓ Deleted {name} AKS cluster"
    error_msg = "Could not delete AKS cluster"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg)
    command = ["az", "group", "delete", "--name", resource_group, "--yes"]
    begin_msg = f"Deleting {name} resource group"
    end_msg = f"✓ Deleted {name} resource group"
    error_msg = "Could not delete resource group"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg)
    # Need to clean kubeconfig context
    reset_current_context_and_attributes()
    return True


def reset_current_context_and_attributes():
    current_context = find_kubectl_current_context()
    cluster_name = find_attribute_in_context(current_context, "cluster")
    user = find_attribute_in_context(current_context, "user")
    delete_kubeconfig_attribute(cluster_name, "cluster")
    delete_kubeconfig_attribute(user, "user")
    unset_kubectl_current_context()


def delete_kubeconfig_attribute(name, attribute="context"):
    command = ["kubectl", "config", f"delete-{attribute}", name]
    run_shell_command(command)


def unset_kubectl_current_context():
    command = ["kubectl", "config", "unset", "current-context"]
    run_shell_command(command)


def apply_calico_manifest(cmd, calico_manifest, workload_cfg,
                          spinner_enter_message, spinner_exit_message, error_message):
    attempts, delay = 100, 3
    with Spinner(cmd, spinner_enter_message, spinner_exit_message):
        command = ["kubectl", "apply", "-f", calico_manifest, "--kubeconfig", workload_cfg]
        # if --verbose, don't capture stderr
        stderr = None if is_verbose() else subprocess.STDOUT
        for _ in range(attempts):
            try:
                subprocess.check_output(command, universal_newlines=True, stderr=stderr)
                break
            except subprocess.CalledProcessError as err:
                logger.info(err)
                time.sleep(delay)
        else:
            raise ResourceNotFoundError(error_message)


def find_kubectl_resource_names(resource_type, error_msg, kubeconfig=None):
    command = ["kubectl", "get", resource_type, "--output", "name"]
    command += add_kubeconfig_to_command(kubeconfig)
    try:
        return run_shell_command(command).splitlines()
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault(error_msg) from err


def find_nodes(kubeconfig):
    error_msg = "Couldn't get nodes of workload cluster"
    return find_kubectl_resource_names("nodes", error_msg, kubeconfig)


def wait_for_nodes(kubeconfig):
    error_msg = "Not all cluster nodes are Ready after 5 minutes."
    wait_for_resource_ready(find_nodes, error_msg, kubeconfig)


def wait_for_resource_ready(find_resources, error_msg, kubeconfig=None,):
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
    error_msg = "Not all machines are Ready after 5 minutes."
    wait_for_resource_ready(find_machines, error_msg, kubeconfig)


def find_machines(kubeconfig=None):
    error_msg = "Couldn't get machines of cluster"
    return find_kubectl_resource_names("machines", error_msg, kubeconfig)


def get_kubeconfig(capi_name):
    cmd = ["clusterctl", "get", "kubeconfig", capi_name]
    # if --verbose, don't capture stderr
    stderr = None if is_verbose() else subprocess.STDOUT
    try:
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=stderr)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't get kubeconfig") from err
    filename = capi_name + ".kubeconfig"
    with open(filename, "w", encoding="utf-8") as kubeconfig_file:
        kubeconfig_file.write(output)
    return f"Wrote kubeconfig file to {filename} "


def delete_workload_cluster(cmd, capi_name, yes=False):
    exit_if_no_management_cluster()
    msg = f'Do you want to delete this Kubernetes cluster "{capi_name}"?'
    if not yes and not prompt_y_n(msg, default="n"):
        return
    cmd = ["kubectl", "delete", "cluster", capi_name]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(cmd), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't delete workload cluster") from err


def list_workload_clusters(cmd):  # pylint: disable=unused-argument
    exit_if_no_management_cluster()
    command = ["kubectl", "get", "clusters", "-o", "json"]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't list workload clusters") from err
    return json.loads(output)


def show_workload_cluster(cmd, capi_name):  # pylint: disable=unused-argument
    exit_if_no_management_cluster()
    # TODO: --output=table could print the output of `clusterctl describe` directly.
    command = ["kubectl", "get", "cluster", capi_name, "--output", "json"]
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault(f"Couldn't get the workload cluster {capi_name}") from err
    return json.loads(output)


def update_workload_cluster(cmd, capi_name):
    raise NotImplementedError


def check_prereqs(cmd, install=False):
    check_kubectl(cmd, install)
    check_clusterctl(cmd, install)

    # Check for required environment variables
    # TODO: remove this when AAD Pod Identity becomes the default
    check_enviroment_variables()


def check_enviroment_variables():
    required_env_vars = ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID"]
    missing_env_vars = [v for v in required_env_vars if not check_environment_var(v)]
    missing_vars_len = len(missing_env_vars)
    if missing_vars_len != 0:
        err_msg = f"Required environment variable {missing_env_vars[0]} was not found."
        if missing_vars_len != 1:
            missing_env_vars = ", ".join(missing_env_vars)
            err_msg = f"Required environment variables {missing_env_vars} were not found."
        raise RequiredArgumentMissingError(err_msg)


def check_environment_var(var):
    var_b64 = var + "_B64"
    val = os.environ.get(var_b64)
    if val:
        logger.info("Found environment variable %s", var_b64)
    else:
        try:
            val = os.environ[var]
        except KeyError:
            return False
        # Set the base64-encoded variable as a convenience
        val = base64.b64encode(val.encode("utf-8")).decode("ascii")
        os.environ[var_b64] = val
        logger.info("Set environment variable %s from %s", var_b64, var)
    return True


def find_management_cluster_retry(cmd, delay=3):
    with Spinner(cmd, "Waiting for Cluster API to be ready", "✓ Cluster API is ready"):
        last_err_msg = None
        for _ in range(0, 10):
            try:
                find_management_cluster()
                break
            except ResourceNotFoundError as err:
                last_err_msg = err.error_msg
                if management_cluster_components_missing_matching_expressions(last_err_msg):
                    raise
                time.sleep(delay)
        else:
            raise ResourceNotFoundError(last_err_msg)
        return True


def management_cluster_components_missing_matching_expressions(output):
    reg_match = [r"namespace: .+?could not be found",
                 r"No resources found in .+?namespace",
                 r"No .+? installation found"]
    for exp in reg_match:
        if match_output(output, exp):
            return True


def find_management_cluster():
    _find_default_cluster()
    components = [
        {
            "namespace": "capz-system",
            "err_msg": "No CAPZ installation found",
            "pod": "capz-controller-manager"
        },
        {
            "namespace": "capi-system",
            "err_msg": "No CAPI installation found",
            "pod": "capi-controller-manager"
        },
        {
            "namespace": "capi-kubeadm-bootstrap-system",
            "err_msg": "No CAPI Kubeadm Bootstrap installation found",
            "pod": "capi-kubeadm-bootstrap-controller-manager"
        },
        {
            "namespace": "capi-kubeadm-control-plane-system",
            "err_msg": "No CAPI Kubeadm Control Plane installation found",
            "pod": "capi-kubeadm-control-plane-controller-manager"
        }
    ]

    for component in components:
        check_kubectl_namespace(component["namespace"])
        check_pods_status_by_namespace(component["namespace"], component["err_msg"], component["pod"])


def check_kubectl_namespace(namespace):
    cmd = ["kubectl", "get", "namespaces", namespace]
    try:
        output = run_shell_command(cmd)
        match = match_output(output, fr"{namespace}.+?Active")
        if match is None:
            raise ResourceNotFoundError(f"namespace: {namespace} status is not Active")
    except subprocess.CalledProcessError as err:
        raise ResourceNotFoundError(f"namespace: {namespace} could not be found!") from err


def _find_default_cluster():
    cmd = ["kubectl", "cluster-info"]
    output = run_shell_command(cmd)
    match = match_output(output, r"Kubernetes .*?is running")
    if match is None:
        raise ResourceNotFoundError("No accessible Kubernetes cluster found")
    return True


def check_pods_status_by_namespace(namespace, error_message, pod_name):
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


def exit_if_no_management_cluster():
    try:
        find_management_cluster()
    except (ResourceNotFoundError, subprocess.CalledProcessError) as err:
        msg = 'No management cluster found. Please create one with "az capi management create".'
        raise UnclassifiedUserFault(msg) from err


def match_output(output, regexp=None):
    if regexp is not None:
        return re.search(regexp, output)
