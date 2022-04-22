# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""This module implements the behavior of `az capi` commands."""

# pylint: disable=missing-docstring

import base64
import json
import logging
import os
import platform
import re
import stat
import subprocess
import time
from functools import lru_cache
from threading import Timer

from azure.cli.core import get_default_cli
from azure.cli.core.api import get_config_dir
from azure.cli.core.azclierror import FileOperationError
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import RequiredArgumentMissingError
from azure.cli.core.azclierror import ResourceNotFoundError
from azure.cli.core.azclierror import UnclassifiedUserFault
from azure.cli.core.azclierror import ValidationError
from jinja2 import Environment, PackageLoader, StrictUndefined
from jinja2.exceptions import UndefinedError
from knack.log import get_logger
from knack.prompting import prompt_choice_list, prompt_y_n
from msrestazure.azure_exceptions import CloudError
from six.moves.urllib.request import urlopen  # pylint: disable=import-error

from ._helpers import ssl_context, urlretrieve
from ._params import _get_default_install_location


logger = get_logger()  # pylint: disable=invalid-name


@lru_cache(maxsize=None)
def is_verbose():
    return any(handler.level <= logging.INFO for handler in logger.handlers)


def init_environment(cmd, prompt=True):
    check_prereqs(cmd, install=True)
    # Create a management cluster if needed
    try:
        find_management_cluster_retry(cmd)
    except ResourceNotFoundError as err:
        if str(err) == "No Cluster API installation found":
            _install_capz_components(cmd)
    except subprocess.CalledProcessError:
        if prompt:
            choices = ["azure - a management cluster in the Azure cloud",
                       "local - a local Docker container-based management cluster",
                       "exit - don't create a management cluster"]
            prompt = """
No Kubernetes cluster was found using the default configuration.

Cluster API needs a "management cluster" to run its components.
Learn more from the Cluster API Book:
https://cluster-api.sigs.k8s.io/user/concepts.html

Where do you want to create a management cluster?
"""
            choice_index = prompt_choice_list(prompt, choices)
        else:
            choice_index = 0
        cluster_name = "capi-manager"
        if choice_index == 0:
            with Spinner(cmd, "Creating Azure resource group", "✓ Created Azure resource group"):
                command = ["az", "group", "create", "-l", "southcentralus", "--name", cluster_name]
                try:
                    output = subprocess.check_output(command, universal_newlines=True)
                    logger.info("%s returned:\n%s", " ".join(command), output)
                except subprocess.CalledProcessError as err:
                    raise UnclassifiedUserFault("Couldn't create Azure resource group") from err
            with Spinner(cmd, "Creating Azure management cluster with AKS", "✓ Created AKS management cluster"):
                command = ["az", "aks", "create", "-g", cluster_name, "--name", cluster_name]
                try:
                    output = subprocess.check_output(command, universal_newlines=True)
                    logger.info("%s returned:\n%s", " ".join(command), output)
                except subprocess.CalledProcessError as err:
                    raise UnclassifiedUserFault("Couldn't create AKS management cluster") from err
        elif choice_index == 1:
            check_kind(cmd, install=not prompt)
            begin_msg = f'Creating local management cluster "{cluster_name}" with kind'
            end_msg = f'✓ Created local management cluster "{cluster_name}"'
            with Spinner(cmd, begin_msg, end_msg):
                command = ["kind", "create", "cluster", "--name", cluster_name]
                try:
                    # if --verbose, don't capture stderr
                    stderr = None if is_verbose() else subprocess.STDOUT
                    output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
                    logger.info("%s returned:\n%s", " ".join(command), output)
                except subprocess.CalledProcessError as err:
                    raise UnclassifiedUserFault("Couldn't create kind management cluster") from err
        else:
            return
        _create_azure_identity_secret(cmd)
        _install_capz_components(cmd)


def _create_azure_identity_secret(cmd):
    secret_name = os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAME"]
    secret_namespace = os.environ["AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"]
    azure_client_secret = os.environ["AZURE_CLIENT_SECRET"]
    with Spinner(cmd, "Creating Cluster Identity Secret", "✓ Created Cluster Indentity Secret"):
        command = ["kubectl", "create", "secret", "generic", secret_name, "--from-literal",
                   f"clientSecret={azure_client_secret}", "--namespace", secret_namespace]
        try:
            # if --verbose, don't capture stderr
            stderr = None if is_verbose() else subprocess.STDOUT
            output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
            logger.info("%s returned:\n%s", " ".join(command), output)
        except subprocess.CalledProcessError as err:
            raise UnclassifiedUserFault("Can't create Cluster Identity Secret") from err


def _install_capz_components(cmd):
    os.environ["EXP_MACHINE_POOL"] = "true"
    os.environ["EXP_CLUSTER_RESOURCE_SET"] = "true"
    with Spinner(cmd, "Initializing management cluster", "✓ Initialized management cluster"):
        command = ["clusterctl", "init", "--infrastructure", "azure"]
        try:
            # if --verbose, don't capture stderr
            stderr = None if is_verbose() else subprocess.STDOUT
            output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
            logger.info("%s returned:\n%s", " ".join(command), output)
        except subprocess.CalledProcessError as err:
            raise UnclassifiedUserFault("Can't locate a Kubernetes cluster") from err


def create_management_cluster(cmd, yes=False):
    check_prereqs(cmd)
    msg = 'Do you want to initialize Cluster API on the current cluster?'
    if not yes and not prompt_y_n(msg, default="n"):
        return

    command = ["clusterctl", "init", "--infrastructure", "azure"]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Can't locate a Kubernetes cluster") from err


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
        vnet_name=None,
        machinepool=False,
        ephemeral_disks=False,
        windows=False,
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
    except CloudError as err:
        if 'could not be found' not in err.message:
            raise
        if not location:
            msg = "--location is required to create the resource group {}."
            raise RequiredArgumentMissingError(msg.format(resource_group_name)) from err

    msg = f'Create the Kubernetes cluster "{capi_name}" in the Azure resource group "{resource_group_name}"?'
    if not yes and not prompt_y_n(msg, default="n"):
        return

    # Set Azure Identity Secret enviroment variables. This will be used in init_environment
    identity_secret_name = "AZURE_CLUSTER_IDENTITY_SECRET_NAME"
    indentity_secret_namespace = "AZURE_CLUSTER_IDENTITY_SECRET_NAMESPACE"
    cluster_identity_name = "CLUSTER_IDENTITY_NAME"
    os.environ[identity_secret_name] = os.environ.get(identity_secret_name, "cluster-identity-secret")
    os.environ[indentity_secret_namespace] = os.environ.get(indentity_secret_namespace, "default")
    os.environ[cluster_identity_name] = os.environ.get(cluster_identity_name, "cluster-identity")

    init_environment(cmd, not yes)

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
        wait_for_ready(workload_cfg)

    return show_workload_cluster(cmd, capi_name)


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


def find_nodes(kubeconfig):
    command = ["kubectl", "get", "nodes", "--output", "name", "--kubeconfig", kubeconfig]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
        return output.splitlines()
    except subprocess.CalledProcessError as err:
        raise UnclassifiedUserFault("Couldn't get nodes of workload cluster") from err


def wait_for_ready(kubeconfig):
    base_command = ["kubectl", "wait", "--for", "condition=Ready", "--kubeconfig", kubeconfig, "--timeout", "10s"]
    timeout = 60 * 5

    # if --verbose, don't capture stderr
    stderr = None if is_verbose() else subprocess.STDOUT
    start = time.time()
    while time.time() < start + timeout:
        command = base_command + find_nodes(kubeconfig)
        try:
            output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
            logger.info("%s returned:\n%s", " ".join(command), output)
            return
        except subprocess.CalledProcessError as err:
            logger.info(err)
            time.sleep(5)
    msg = "Not all cluster nodes are Ready after 5 minutes."
    raise ResourceNotFoundError(msg)


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
    for var in ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID"]:
        check_environment_var(var)


class Spinner():

    def __init__(self, cmd, begin_msg="In Progress", end_msg=" ✓ Finished"):
        self._controller = cmd.cli_ctx.get_progress_controller()
        self.begin_msg, self.end_msg = begin_msg, end_msg
        self.tick()

    def begin(self, **kwargs):
        if not is_verbose():
            self._controller.begin(**kwargs)

    def end(self, **kwargs):
        self._controller.end(**kwargs)

    def tick(self):
        if not is_verbose() and self._controller.is_running():
            Timer(0.25, self.tick).start()
            self.update()

    def update(self):
        self._controller.update()

    def __enter__(self):
        self._controller.begin(message=self.begin_msg)
        logger.info(self.begin_msg)
        return self

    def __exit__(self, _type, value, traceback):
        if traceback:
            logger.debug(traceback)
            self._controller.end()
        else:
            self._controller.end(message=self.end_msg)
            logger.warning(self.end_msg)


def check_clusterctl(cmd, install=False):
    if not which("clusterctl"):
        logger.info("clusterctl was not found.")
        if install or prompt_y_n("Download and install clusterctl?", default="n"):
            with Spinner(cmd, "Downloading clusterctl", "✓ Downloaded clusterctl"):
                install_clusterctl(cmd)


def check_kind(cmd, install=False):
    if not which("kind"):
        logger.info("kind was not found.")
        if install or prompt_y_n("Download and install kind?", default="n"):
            with Spinner(cmd, "Downloading kind", "✓ Downloaded kind"):
                install_kind(cmd)


def check_kubectl(cmd, install=False):
    if not which("kubectl"):
        logger.info("kubectl was not found.")
        if install or prompt_y_n("Download and install kubectl?", default="n"):
            with Spinner(cmd, "Downloading kubectl", "✓ Downloaded kubectl"):
                install_kubectl(cmd)


def check_environment_var(var):
    var_b64 = var + "_B64"
    val = os.environ.get(var_b64)
    if val:
        logger.info("Found environment variable %s", var_b64)
    else:
        try:
            val = os.environ[var]
        except KeyError as err:
            raise RequiredArgumentMissingError(f"Required environment variable {err} was not found.") from err
        # Set the base64-encoded variable as a convenience
        val = base64.b64encode(val.encode("utf-8")).decode("ascii")
        os.environ[var_b64] = val
        logger.info("Set environment variable %s from %s", var_b64, var)


def find_management_cluster_retry(cmd, delay=3):
    with Spinner(cmd, "Waiting for Cluster API to be ready", "✓ Cluster API is ready"):
        for _ in range(0, 100):
            try:
                find_management_cluster()
                break
            except ResourceNotFoundError:
                time.sleep(delay)
        else:
            return False
        return True


def find_management_cluster():
    cmd = ["kubectl", "cluster-info"]
    match = check_cmd(cmd, r"Kubernetes .*?is running")
    if match is None:
        raise ResourceNotFoundError("No accessible Kubernetes cluster found")
    check_pods_status_by_namespace("capz-system", "No CAPZ installation found", "capz-controller-manager")
    check_pods_status_by_namespace("capi-system", "No CAPI installation found", "capi-controller-manager")
    check_pods_status_by_namespace("capi-kubeadm-bootstrap-system",
                                   "No CAPI Kubeadm Bootstrap installation found",
                                   "capi-kubeadm-bootstrap-controller-manager")
    check_pods_status_by_namespace("capi-kubeadm-control-plane-system",
                                   "No CAPI Kubeadm Control Plane installation found",
                                   "capi-kubeadm-control-plane-controller-manager")


def check_pods_status_by_namespace(namespace, error_message, pod_name):
    cmd = ["kubectl", "get", "pods", "--namespace", namespace]
    try:
        match = check_cmd(cmd, fr"{pod_name}-.+?Running")
        if match is None:
            raise ResourceNotFoundError(error_message)
    except subprocess.CalledProcessError as err:
        logger.error(err)


def exit_if_no_management_cluster():
    try:
        find_management_cluster()
    except (ResourceNotFoundError, subprocess.CalledProcessError) as err:
        msg = 'No management cluster found. Please create one with "az capi management create".'
        raise UnclassifiedUserFault(msg) from err


def check_cmd(command, regexp=None):
    output = subprocess.check_output(command, universal_newlines=True, stderr=subprocess.STDOUT)
    logger.info("%s returned:\n%s", " ".join(command), output)
    if regexp is not None:
        return re.search(regexp, output)
    return False


def which(binary):
    path_var = os.getenv("PATH")

    if platform.system() == "Windows":
        binary += ".exe"
        parts = path_var.split(";")
    else:
        parts = path_var.split(":")

    for part in parts:
        bin_path = os.path.join(part, binary)
        if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
            return bin_path

    return None


def install_clusterctl(_cmd, client_version="latest", install_location=None, source_url=None):
    """
    Install clusterctl, a command-line interface for Cluster API Kubernetes clusters.
    """

    if not source_url:
        source_url = "https://github.com/kubernetes-sigs/cluster-api/releases/"
        # TODO: mirror clusterctl binary to Azure China cloud--see install_kubectl().

    if client_version != "latest":
        source_url += "tags/"
    source_url += "{}/download/clusterctl-{}-amd64"

    file_url = ""
    system = platform.system()
    if system in ("Darwin", "Linux"):
        file_url = source_url.format(client_version, system.lower())
    else:  # TODO: support Windows someday?
        raise ValidationError(f'The clusterctl binary is not available for "{system}"')

    # ensure installation directory exists
    if install_location is None:
        install_location = _get_default_install_location("clusterctl")
    install_dir, cli = os.path.dirname(install_location), os.path.basename(
        install_location
    )
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    return download_binary(install_location, install_dir, file_url, system, cli)


def install_kind(_cmd, client_version="v0.10.0", install_location=None, source_url=None):
    """
    Install kind, a container-based Kubernetes environment for development and testing.
    """

    if not source_url:
        source_url = "https://kind.sigs.k8s.io/dl/{}/kind-{}-amd64"

    # ensure installation directory exists
    if install_location is None:
        install_location = _get_default_install_location("kind")
    install_dir, cli = os.path.dirname(install_location), os.path.basename(
        install_location
    )
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    file_url = ""
    system = platform.system()
    if system == "Windows":
        file_url = source_url.format(client_version, "windows")
    elif system == "Linux":
        file_url = source_url.format(client_version, "linux")
    elif system == "Darwin":
        file_url = source_url.format(client_version, "darwin")
    else:
        raise InvalidArgumentValueError(f'System "{system}" is not supported by kind.')

    return download_binary(install_location, install_dir, file_url, system, cli)


def install_kubectl(cmd, client_version="latest", install_location=None, source_url=None):
    """
    Install kubectl, a command-line interface for Kubernetes clusters.
    """

    if not source_url:
        source_url = "https://storage.googleapis.com/kubernetes-release/release"
        cloud_name = cmd.cli_ctx.cloud.name
        if cloud_name.lower() == "azurechinacloud":
            source_url = "https://mirror.azure.cn/kubernetes/kubectl"

    if client_version == "latest":
        with urlopen(source_url + "/stable.txt", context=ssl_context()) as f:
            client_version = f.read().decode("utf-8").strip()
    else:
        client_version = f"v{client_version}"

    file_url = ""
    system = platform.system()
    base_url = source_url + "/{}/bin/{}/amd64/{}"

    # ensure installation directory exists
    if install_location is None:
        install_location = _get_default_install_location("kubectl")
    install_dir, cli = os.path.dirname(install_location), os.path.basename(
        install_location
    )
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    if system == "Windows":
        file_url = base_url.format(client_version, "windows", "kubectl.exe")
    elif system == "Linux":
        # TODO: Support ARM CPU here
        file_url = base_url.format(client_version, "linux", "kubectl")
    elif system == "Darwin":
        file_url = base_url.format(client_version, "darwin", "kubectl")
    else:
        raise InvalidArgumentValueError(
            f"Proxy server ({system}) does not exist on the cluster."
        )

    return download_binary(install_location, install_dir, file_url, system, cli)


def download_binary(install_location, install_dir, file_url, system, cli):

    logger.info('Downloading client to "%s" from "%s"', install_location, file_url)
    try:
        urlretrieve(file_url, install_location)
        os.chmod(
            install_location,
            os.stat(install_location).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
    except IOError as ex:
        err_msg = f"Connection error while attempting to download client ({ex})"
        raise FileOperationError(err_msg) from ex

    if system == "Windows":
        # be verbose, as the install_location is likely not in Windows's search PATHs
        env_paths = os.environ["PATH"].split(";")
        found = next(
            (x for x in env_paths if x.lower().rstrip("\\") == install_dir.lower()),
            None,
        )
        if not found:
            # pylint: disable=logging-format-interpolation
            logger.warning(
                'Please add "%s" to your search PATH so the `%s` can be found. 2 options: \n'
                '    1. Run "set PATH=%%PATH%%;%s" or "$env:path += \'%s\'" for PowerShell. '
                "This is good for the current command session.\n"
                "    2. Update system PATH environment variable by following "
                '"Control Panel->System->Advanced->Environment Variables", and re-open the command window. '
                "You only need to do it once",
                install_dir, cli, install_dir, install_dir,
            )
    else:
        if not which(cli):
            logger.warning(
                "Please ensure that %s is in your search PATH, so the `%s` command can be found.",
                install_dir,
                cli,
            )
    return install_location
