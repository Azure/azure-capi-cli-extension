# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""This module implements the behavior of `az capi` commands."""

# pylint: disable=missing-docstring

import base64
import json
import os
import subprocess
import time
import re
import yaml

import azext_capi.helpers.kubectl as kubectl_helpers
import semver

from azure.cli.core import get_default_cli
from azure.cli.core.api import get_config_dir
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import RequiredArgumentMissingError
from azure.core.exceptions import ResourceNotFoundError as ResourceNotFoundException
from azure.cli.core.azclierror import ResourceNotFoundError
from azure.cli.core.azclierror import UnclassifiedUserFault
from azure.cli.core.azclierror import MutuallyExclusiveArgumentError
from jinja2 import Environment, PackageLoader, StrictUndefined
from jinja2.exceptions import UndefinedError
from knack.prompting import prompt_choice_list, prompt_y_n
from msrestazure.azure_exceptions import CloudError

from ._format import output_for_tsv, output_list_for_tsv
from .helpers.generic import has_kind_prefix
from .helpers.logger import logger
from .helpers.spinner import Spinner
from .helpers.run_command import run_shell_command, try_command_with_spinner
from .helpers.binary import check_clusterctl, check_kubectl, check_kind
from .helpers.prompt import get_cluster_name_by_user_prompt, get_user_prompt_or_default
from .helpers.generic import match_output, is_clusterctl_compatible
from .helpers.os import set_environment_variables, write_to_file
from .helpers.network import urlretrieve
from .helpers.constants import MANAGEMENT_RG_NAME


def init_environment(cmd, prompt=True, management_cluster_name=None,
                     resource_group_name=None, location=None, tags=""):
    check_prereqs(cmd, install=True)
    # Create a management cluster if needed
    use_new_cluster = False
    pre_prompt = None
    try:
        find_management_cluster_retry(cmd)
        cluster_name = kubectl_helpers.find_cluster_in_current_context()
        if prompt and not prompt_y_n(f"Do you want to use {cluster_name} as the management cluster?"):
            use_new_cluster = True
        else:
            return True
    except ResourceNotFoundError as err:
        error_msg = err.error_msg
        if management_cluster_components_missing_matching_expressions(error_msg):
            choices = ["Create a new management cluster",
                       "Use default kubernetes cluster found and install CAPI required components",
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
                                                             pre_prompt_text=pre_prompt, prompt=prompt, tags=tags):
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
    command += kubectl_helpers.add_kubeconfig_to_command(kubeconfig)
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg, True)


def _install_capi_provider_components(cmd, kubeconfig=None):
    os.environ["EXP_MACHINE_POOL"] = "true"
    os.environ["EXP_CLUSTER_RESOURCE_SET"] = "true"
    begin_msg = "Initializing management cluster"
    end_msg = "✓ Initialized management cluster"
    error_msg = "Couldn't install CAPI provider components in current cluster"
    command = ["clusterctl", "init", "--infrastructure", "azure"]
    command += kubectl_helpers.add_kubeconfig_to_command(kubeconfig)
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg)


def create_resource_group(cmd, rg_name, location, yes=False, tags=""):
    msg = f'Create the Azure resource group "{rg_name}" in location "{location}"?'
    if yes or prompt_y_n(msg, default="n"):
        command = ["az", "group", "create", "-l", location, "-n", rg_name, "--tags", tags]
        begin_msg = f"Creating Resource Group: {rg_name}"
        end_msg = f"✓ Created Resource Group: {rg_name}"
        err_msg = f"Could not create resource group {rg_name}"
        try_command_with_spinner(cmd, command, begin_msg, end_msg, err_msg)
        return True
    return False


def create_management_cluster(cmd, cluster_name=None, resource_group_name=None, location=None,
                              yes=False):
    check_prereqs(cmd)
    existing_cluster = kubectl_helpers.find_cluster_in_current_context()
    found_cluster = False
    if existing_cluster:
        msg = f'Do you want to initialize Cluster API on the current cluster {existing_cluster}?'
        if yes or prompt_y_n(msg, default="n"):
            try:
                kubectl_helpers.find_default_cluster()
                found_cluster = True
            except subprocess.CalledProcessError as err:
                raise UnclassifiedUserFault("Can't locate a Kubernetes cluster") from err
    if not found_cluster and not create_new_management_cluster(cmd, cluster_name, resource_group_name,
                                                               location, prompt=not yes):
        return
    set_azure_identity_secret_env_vars()
    _create_azure_identity_secret(cmd)
    _install_capi_provider_components(cmd)


def create_aks_management_cluster(cmd, cluster_name, resource_group_name=None, location=None, yes=False, tags=""):
    if not resource_group_name:
        msg = "Please name the resource group for the management cluster"
        resource_group_name = get_user_prompt_or_default(msg, cluster_name, skip_prompt=yes)
    if not location:
        default_location = "southcentralus"
        msg = f"Please provide a location for {resource_group_name} resource group"
        location = get_user_prompt_or_default(msg, default_location, skip_prompt=yes)
    if not create_resource_group(cmd, resource_group_name, location, yes, tags):
        return False
    command = ["az", "aks", "create", "-g", resource_group_name, "--name", cluster_name, "--generate-ssh-keys",
               "--network-plugin", "azure", "--network-policy", "calico", "--node-count", "1", "--tags", tags]
    try_command_with_spinner(cmd, command, "Creating Azure management cluster with AKS",
                             "✓ Created AKS management cluster", "Couldn't create AKS management cluster")
    os.environ[MANAGEMENT_RG_NAME] = resource_group_name
    logger.warning("aks credentials will overwrite existing cluster config for cluster %s if it exists", cluster_name)
    with Spinner(cmd, "Obtaining AKS credentials", "✓ Obtained AKS credentials"):
        command = ["az", "aks", "get-credentials", "-g", resource_group_name, "--name", cluster_name,
                   "--overwrite-existing"]
        try:
            subprocess.check_call(command, universal_newlines=True)
        except subprocess.CalledProcessError as err:
            raise UnclassifiedUserFault("Couldn't get credentials for AKS management cluster") from err
    return True


def create_new_management_cluster(cmd, cluster_name=None, resource_group_name=None,
                                  location=None, pre_prompt_text=None, prompt=True, tags=""):
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
                                             location, yes=not prompt, tags=tags):
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


def find_resource_group_name_of_aks_cluster(cluster_name):
    jmespath_query = "[].{name:name, group:resourceGroup}"
    command = ["az", "aks", "list", "--query", jmespath_query]
    result = run_shell_command(command)
    result = json.loads(result)
    result = [item for item in result if item['name'] == cluster_name]
    if result:
        return result[0]["group"]
    return None


def delete_management_cluster(cmd, yes=False):  # pylint: disable=unused-argument
    exit_if_no_management_cluster()
    cluster_name = kubectl_helpers.find_cluster_in_current_context()

    msg = f"Do you want to delete {cluster_name} cluster?"

    cluster_resource_group = None
    is_kind_cluster = has_kind_prefix(cluster_name)
    if not is_kind_cluster:
        cluster_resource_group = find_resource_group_name_of_aks_cluster(cluster_name)
        if not cluster_resource_group:
            prompt = f"Please enter resource group name of {cluster_name} AKS cluster: "
            cluster_resource_group = get_user_prompt_or_default(prompt, cluster_name, skip_prompt=yes)
            msg = f"Do you want to delete {cluster_name} cluster and resource group {cluster_resource_group}?"

    pre_workload_warning = f"""\
Please make sure to delete all workload clusters managed by {cluster_name} management cluster before proceeding \
to prevent any orphan workload cluster
"""
    msg = pre_workload_warning + msg
    if not yes and not prompt_y_n(msg, default="n"):
        return

    if is_kind_cluster:
        delete_kind_cluster_from_current_context(cmd)
    else:
        delete_aks_cluster(cmd, cluster_name, cluster_resource_group)


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
        output = run_shell_command(command)
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
        "v1beta1",
    ]
    try:
        run_shell_command(command)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't upgrade management cluster") from err


def set_azure_identity_secret_env_vars():
    identity_secret_name = "AZURE_CLUSTER_IDENTITY_SECRET_NAME"
    identity_secret_namespace = "AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"
    cluster_identity_name = "CLUSTER_IDENTITY_NAME"
    os.environ[identity_secret_name] = os.environ.get(identity_secret_name, "cluster-identity-secret")
    os.environ[identity_secret_namespace] = os.environ.get(identity_secret_namespace, "default")
    os.environ[cluster_identity_name] = os.environ.get(cluster_identity_name, "cluster-identity")


def generate_workload_cluster_configuration(cmd, filename, args, user_provided_template=None):
    end_msg = f'✓ Generated workload cluster configuration at "{filename}"'
    with Spinner(cmd, "Generating workload cluster configuration", end_msg):
        manifest = None
        try:
            if user_provided_template:
                manifest = render_custom_cluster_template(user_provided_template, filename, args)
            else:
                manifest = render_builtin_jinja_template(args)
            write_to_file(filename, manifest)
        except subprocess.CalledProcessError as err:
            msg = "Could not generate workload cluster configuration."
            raise UnclassifiedUserFault(msg) from err


def render_builtin_jinja_template(args):
    """
    Use the built-in template and process it with Jinja
    """
    env = Environment(loader=PackageLoader("azext_capi", "templates"),
                      auto_reload=False, undefined=StrictUndefined)
    logger.debug("Available templates: %s", env.list_templates())
    jinja_template = env.get_template("base.jinja")
    try:
        return jinja_template.render(args)
    except UndefinedError as err:
        msg = f"Could not generate workload cluster configuration.\n{err}"
        raise RequiredArgumentMissingError(msg) from err


def render_custom_cluster_template(template, filename, args=None):
    """
    Fetch a user-defined template and process it with "clusterctl generate"
    """
    set_environment_variables(args)
    command = ["clusterctl", "generate", "yaml", "--from"]
    if not is_clusterctl_compatible(template):
        # download file so clusterctl can use a local file
        file_name = f"raw-{filename}"
        urlretrieve(template, file_name)
        template = file_name
    command += [template]
    try:
        return run_shell_command(command)
    except subprocess.CalledProcessError as err:
        err_command_list = err.args[1]
        err_command_name = err_command_list[0]
        if err_command_name == "clusterctl":
            error_variables = re.search(r"(?<=\[).+?(?=\])", err.stdout)[0]
            msg = "Could not generate workload cluster configuration."
            msg += f"\nPlease set the following environment variables:\n{error_variables}"
        raise RequiredArgumentMissingError(msg) from err


def get_default_bootstrap_commands(windows=False):
    '''
    Returns a dictionary with default pre- and post-bootstrap VM commands
    '''
    pre_bootstrap_cmds = []
    post_bootstrap_cmds = ["nssm set kubelet start SERVICE_AUTO_START",
                           "powershell C:/defender-exclude-calico.ps1"] if windows else []
    bootstrap_cmds = {
        "pre": pre_bootstrap_cmds,
        "post": post_bootstrap_cmds
    }
    return bootstrap_cmds


def parse_bootstrap_commands_from_file(file_path):
    pre_commands, post_commands = [], []
    if not os.path.isfile(file_path):
        raise InvalidArgumentValueError("Invalid boostrap command file")
    file_result = None
    with open(file_path, "r", encoding="utf-8") as file:
        file_result = yaml.safe_load(file)
    for key, value in file_result.items():
        if not value:
            continue
        if key == "preBootstrapCommands":
            pre_commands = [value] if isinstance(value, str) else value
        elif key == "postBootstrapCommands":
            post_commands = [value] if isinstance(value, str) else value
    result = {
        "pre": pre_commands,
        "post": post_commands
    }
    return result


def check_resource_group(cmd, resource_group_name, default_resource_group_name, location=None):
    """
    Check if the RG already exists and that it's consistent with the location
    specified. CAPZ will actually create (and delete) the RG if needed.
    """
    from ._client_factory import cf_resource_groups  # pylint: disable=import-outside-toplevel

    rg_client = cf_resource_groups(cmd.cli_ctx)
    if not resource_group_name:
        resource_group_name = default_resource_group_name
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
    return resource_group_name


# pylint: disable=inconsistent-return-statements
def create_workload_cluster(  # pylint: disable=too-many-arguments,too-many-locals,too-many-statements
        cmd,
        capi_name=None,
        resource_group_name=None,
        location=None,
        control_plane_machine_type=os.environ.get("AZURE_CONTROL_PLANE_MACHINE_TYPE", "Standard_D2s_v3"),
        control_plane_machine_count=os.environ.get("CONTROL_PLANE_MACHINE_COUNT", 3),
        node_machine_type=os.environ.get("AZURE_NODE_MACHINE_TYPE", "Standard_D2s_v3"),
        node_machine_count=os.environ.get("WORKER_MACHINE_COUNT", 3),
        kubernetes_version=os.environ.get("KUBERNETES_VERSION", "v1.22.8"),
        ssh_public_key=os.environ.get("AZURE_SSH_PUBLIC_KEY", ""),
        external_cloud_provider=False,
        management_cluster_name=None,
        management_cluster_resource_group_name=None,
        vnet_name=None,
        machinepool=False,
        ephemeral_disks=False,
        windows=False,
        pivot=False,
        user_provided_template=None,
        bootstrap_commands=None,
        yes=False,
        tags=""):

    if location is None:
        location = os.environ.get("AZURE_LOCATION", None)

    if not capi_name:
        from .helpers.names import generate_cluster_name
        capi_name = generate_cluster_name()
        logger.warning('Using generated cluster name "%s"', capi_name)

    if not kubernetes_version.startswith('v'):
        kubernetes_version = f'v{kubernetes_version}'
    try:
        semver.parse(kubernetes_version[1:])
    except ValueError as err:
        raise InvalidArgumentValueError(f'Invalid Kubernetes version: "{kubernetes_version}"') from err

    if user_provided_template:
        mutual_exclusive_args = [
            {
                "name": "external_cloud_provider",
                "value": external_cloud_provider
            },
            {
                "name": "machinepool",
                "value": machinepool
            },
            {
                "name": "ephemeral_disks",
                "value": ephemeral_disks
            }
        ]
        defined_args = [v["name"] for v in mutual_exclusive_args if v["value"]]
        if defined_args:
            defined_args = " ,".join(defined_args)
            error_msg = f'The following arguments are incompatible with "--template":\n{defined_args}'
            raise MutuallyExclusiveArgumentError(error_msg)

    bootstrap_cmds = get_default_bootstrap_commands(windows)

    if bootstrap_commands:
        kubeadm_file_commands = parse_bootstrap_commands_from_file(bootstrap_commands)
        bootstrap_cmds["pre"] += kubeadm_file_commands["pre"]
        bootstrap_cmds["post"] += kubeadm_file_commands["post"]

    resource_group_name = check_resource_group(cmd, resource_group_name, capi_name, location)

    msg = f'Create the Kubernetes cluster "{capi_name}" in the Azure resource group "{resource_group_name}"?'
    if not yes and not prompt_y_n(msg, default="n"):
        return

    # Set Azure Identity Secret enviroment variables. This will be used in init_environment
    set_azure_identity_secret_env_vars()

    if not init_environment(cmd, not yes, management_cluster_name, management_cluster_resource_group_name,
                            location, tags):
        return

    # Generate the cluster configuration
    ssh_public_key_b64 = ""
    if ssh_public_key:
        ssh_public_key_b64 = base64.b64encode(ssh_public_key.encode("utf-8"))
        ssh_public_key_b64 = str(ssh_public_key_b64, "utf-8")

    args = {
        "AZURE_CONTROL_PLANE_MACHINE_TYPE": control_plane_machine_type,
        "AZURE_LOCATION": location,
        "AZURE_NODE_MACHINE_TYPE": node_machine_type,
        "AZURE_RESOURCE_GROUP": resource_group_name,
        "AZURE_SSH_PUBLIC_KEY": ssh_public_key,
        "AZURE_SSH_PUBLIC_KEY_B64": ssh_public_key_b64,
        "AZURE_VNET_NAME": vnet_name,
        "CLUSTER_NAME": capi_name,
        "CONTROL_PLANE_MACHINE_COUNT": control_plane_machine_count,
        "KUBERNETES_VERSION": kubernetes_version,
        "WORKER_MACHINE_COUNT": node_machine_count,
        "NODEPOOL_TYPE": "machinepool" if machinepool else "machinedeployment",
        "CLUSTER_IDENTITY_NAME": os.environ["CLUSTER_IDENTITY_NAME"],
        "AZURE_SUBSCRIPTION_ID": os.environ['AZURE_SUBSCRIPTION_ID'],
        "AZURE_TENANT_ID": os.environ["AZURE_TENANT_ID"],
        "AZURE_CLIENT_ID": os.environ["AZURE_CLIENT_ID"],
        "AZURE_CLUSTER_IDENTITY_SECRET_NAME": os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAME"],
        "AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE": os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"],
        "PRE_BOOTSTRAP_CMDS": bootstrap_cmds["pre"],
        "POST_BOOTSTRAP_CMDS": bootstrap_cmds["post"],
    }

    if not user_provided_template:
        jinja_extra_args = {
            "EXTERNAL_CLOUD_PROVIDER": external_cloud_provider,
            "WINDOWS": windows,
            "EPHEMERAL": ephemeral_disks,
        }
        args.update(jinja_extra_args)

    filename = capi_name + ".yaml"
    generate_workload_cluster_configuration(cmd, filename, args, user_provided_template)

    # Apply the cluster configuration.
    attempts, delay = 100, 3
    begin_msg = f'Creating workload cluster "{capi_name}"'
    end_msg = f'✓ Created workload cluster "{capi_name}"'
    with Spinner(cmd, begin_msg, end_msg):
        command = ["kubectl", "apply", "-f", filename]
        for _ in range(attempts):
            try:
                run_shell_command(command)
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
                kubectl_helpers.get_kubeconfig(capi_name)
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

    apply_kubernetes_manifest(cmd, calico_manifest, workload_cfg, spinner_enter_message,
                              spinner_exit_message, error_message)

    if windows:
        calico_manifest = "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api-provider-azure/main/templates/addons/windows/calico/calico.yaml"  # pylint: disable=line-too-long
        spinner_enter_message = "Deploying Windows Calico support"
        spinner_exit_message = "✓ Deployed Windows Calico support to workload cluster"
        error_message = "Couldn't install Windows Calico support after waiting 5 minutes."
        apply_kubernetes_manifest(cmd, calico_manifest, workload_cfg, spinner_enter_message,
                                  spinner_exit_message, error_message)

        kubeproxy_manifest_url = "https://github.com/kubernetes-sigs/cluster-api-provider-azure/blob/main/templates/addons/windows/calico/kube-proxy-windows.yaml"  # pylint: disable=line-too-long
        kubeproxy_manifest_file = "kube-proxy-windows.yaml"
        manifest = render_custom_cluster_template(kubeproxy_manifest_url, kubeproxy_manifest_file, args)
        write_to_file(kubeproxy_manifest_file, manifest)

        spinner_enter_message = "Deploying Windows kube-proxy support"
        spinner_exit_message = "✓ Deployed Windows kube-proxy support to workload cluster"
        error_message = "Couldn't install Windows kube-proxy support after waiting 5 minutes."
        apply_kubernetes_manifest(cmd, kubeproxy_manifest_file, workload_cfg, spinner_enter_message,
                                  spinner_exit_message, error_message)

    # Wait for all nodes to be ready before returning
    with Spinner(cmd, "Waiting for workload cluster nodes to be ready", "✓ Workload cluster is ready"):
        kubectl_helpers.wait_for_nodes(workload_cfg)

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
        kubectl_helpers.wait_for_machines()

    command = ["clusterctl", "move", "--to-kubeconfig", target_cluster_kubeconfig]
    begin_msg = "Moving cluster objects into target cluster"
    end_msg = "✓ Moved cluster objects into target cluster"
    error_msg = "Could not complete clusterctl move action"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg, True)

    cluster_name = kubectl_helpers.find_cluster_in_current_context()
    if has_kind_prefix(cluster_name):
        delete_kind_cluster_from_current_context(cmd)
    else:
        resource_group = os.environ.get(MANAGEMENT_RG_NAME, None)
        if not resource_group:
            raise UnclassifiedUserFault("Could not delete AKS management cluster, resource group missing")
        delete_aks_cluster(cmd, cluster_name, resource_group)

    # Merge workload cluster kubeconfig and default kubeconfig.
    # To preverse any previous existing contexts
    kubectl_helpers.merge_kubeconfig(target_cluster_kubeconfig)
    logger.warning("Completed Pivot Process")
    return True


def delete_kind_cluster(cmd, name):
    command = ["kind", "delete", "cluster", "--name", name]
    begin_msg = f"Deleting {name} kind cluster"
    end_msg = f"✓ Deleted {name} kind cluster"
    error_msg = "Could not delete kind cluster"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, error_msg)


def delete_kind_cluster_from_current_context(cmd):
    cluster_name = kubectl_helpers.find_cluster_in_current_context()
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
    kubectl_helpers.reset_current_context_and_attributes()
    return True


def apply_kubernetes_manifest(cmd, manifest, workload_cfg,
                              spinner_enter_message, spinner_exit_message, error_message):
    attempts, delay = 100, 3
    with Spinner(cmd, spinner_enter_message, spinner_exit_message):
        command = ["kubectl", "apply", "-f", manifest, "--kubeconfig", workload_cfg]
        for _ in range(attempts):
            try:
                run_shell_command(command)
                break
            except subprocess.CalledProcessError as err:
                logger.info(err)
                time.sleep(delay)
        else:
            raise ResourceNotFoundError(error_message)


def delete_workload_cluster(cmd, capi_name, resource_group_name=None, yes=False):
    exit_if_no_management_cluster()
    msg = f'Do you want to delete this Kubernetes cluster "{capi_name}"?'
    command = ["kubectl", "delete", "cluster", capi_name]
    is_self_managed = is_self_managed_cluster(capi_name)
    if is_self_managed:
        if not resource_group_name:
            resource_group_name = get_azure_resource_group_from_azure_cluster(capi_name)
        msg = f'Do you want to delete the {capi_name} Kubernetes cluster and {resource_group_name} resource group?'
        command = ["az", "group", "delete", "-n", resource_group_name, '-y']
    if not yes and not prompt_y_n(msg, default="n"):
        return
    begin_msg = "Deleting workload cluster"
    end_msg = "✓ Deleted workload cluster"
    if capi_name == kubectl_helpers.find_cluster_in_current_context():
        end_msg += f'\nNote: To also delete the management cluster, run "az capi management delete -n {capi_name}"'
    err_msg = "Couldn't delete workload cluster"
    try_command_with_spinner(cmd, command, begin_msg, end_msg, err_msg)
    if is_self_managed:
        kubectl_helpers.reset_current_context_and_attributes()


def get_azure_resource_group_from_azure_cluster(cluster_name, kubeconfig=None):
    output = kubectl_helpers.get_azure_cluster(cluster_name, kubeconfig)
    output = json.loads(output)
    return output["spec"]["resourceGroup"]


def is_self_managed_cluster(cluster_name):
    management_cluster_ports = kubectl_helpers.get_ports_cluster()
    workload_cluster_ports = kubectl_helpers.get_ports_cluster(f"{cluster_name}.kubeconfig")
    return management_cluster_ports == workload_cluster_ports


def list_workload_clusters(cmd):  # pylint: disable=unused-argument
    exit_if_no_management_cluster()
    command = ["kubectl", "get", "clusters", "-o", "json"]
    try:
        output = run_shell_command(command)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't list workload clusters") from err
    if tab_separated_output(cmd):
        return output_list_for_tsv(output)
    return json.loads(output)


def tab_separated_output(cmd):
    """Returns True if "--output tsv" was specified without a "--query" argument."""
    data = cmd.cli_ctx.invocation.data
    return "query" not in data and data.get("output") == "tsv"


def show_workload_cluster(cmd, capi_name):  # pylint: disable=unused-argument
    exit_if_no_management_cluster()
    # TODO: --output=table could print the output of `clusterctl describe` directly.
    command = ["kubectl", "get", "cluster", capi_name, "--output", "json"]
    try:
        output = run_shell_command(command)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault(f"Couldn't get the workload cluster {capi_name}") from err
    if tab_separated_output(cmd):
        return output_for_tsv(output)
    return json.loads(output)


def update_workload_cluster(cmd, capi_name):
    raise NotImplementedError


def install_tools(cmd, all_tools=False, install_path=None):
    if all_tools:
        logger.info('Checking if required tools are installed')
        check_tools(cmd, install=True, install_path=install_path)
    else:
        logger.warning('Installing individual tools is not currently supported')


def check_tools(cmd, install=False, install_path=None):
    check_kubectl(cmd, install=install, install_path=install_path)
    check_clusterctl(cmd, install=install, install_path=install_path)


def check_prereqs(cmd, install=False):
    check_tools(cmd, install)

    # Check for required environment variables
    # TODO: remove this when AAD Pod Identity becomes the default
    check_environment_variables()


def check_environment_variables():
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
    kubectl_helpers.find_default_cluster()
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
        kubectl_helpers.check_kubectl_namespace(component["namespace"])
        kubectl_helpers.check_pods_status_by_namespace(component["namespace"], component["err_msg"], component["pod"])


def exit_if_no_management_cluster():
    try:
        find_management_cluster()
    except (ResourceNotFoundError, subprocess.CalledProcessError) as err:
        msg = 'No management cluster found. Please create one with "az capi management create".'
        raise UnclassifiedUserFault(msg) from err
