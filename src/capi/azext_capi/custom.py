# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""This module implements the behavior of `az capi` commands."""

# pylint: disable=missing-docstring

import base64
import os
import platform
import random
import re
import ssl
import stat
import string
import subprocess
import sys
import time

from jinja2 import Environment, PackageLoader
from knack.log import get_logger
from knack.prompting import prompt_choice_list, prompt_y_n
from knack.util import CLIError
from six.moves.urllib.request import urlopen  # pylint: disable=import-error

from azure.cli.core import get_default_cli
from azure.cli.core.util import in_cloud_console
from azure.cli.core.api import get_config_dir

from ._params import _get_default_install_location


logger = get_logger(__name__)  # pylint: disable=invalid-name


def init_environment(cmd):
    check_preqreqs(cmd, install=True)
    # Create a management cluster if needed
    try:
        find_management_cluster_retry(cmd.cli_ctx)
    except CLIError as err:
        if str(err) == "No CAPZ installation found":
            _install_capz_components(cmd)
    except subprocess.CalledProcessError:
        providers = ['AKS - a managed cluster in Azure',
                     'kind - a local docker-based cluster', "exit - don't create a management cluster"]
        prompt = """\
No Kubernetes cluster was found using the default configuration.

Cluster API needs a "management cluster" to run its components.
Learn more from the Cluster API Book:
  https://cluster-api.sigs.k8s.io/user/concepts.html

Where should we create a management cluster?
"""
        choice_index = prompt_choice_list(prompt, providers)
        random_id = ''.join(random.choices(
            string.ascii_lowercase + string.digits, k=6))
        cluster_name = "capi-manager-" + random_id
        if choice_index == 0:
            logger.info("AKS management cluster")
            cmd = ["az", "group", "create", "-l",
                   "southcentralus", "--name", cluster_name]
            try:
                output = subprocess.check_output(cmd, universal_newlines=True)
                logger.info("%s returned:\n%s", " ".join(cmd), output)
            except subprocess.CalledProcessError as err:
                raise CLIError(err)
            cmd = ["az", "aks", "create", "-g",
                   cluster_name, "--name", cluster_name]
            try:
                output = subprocess.check_output(cmd, universal_newlines=True)
                logger.info("%s returned:\n%s", " ".join(cmd), output)
            except subprocess.CalledProcessError as err:
                raise CLIError(err)
        elif choice_index == 1:
            logger.info("kind management cluster")
            # Install kind
            kind_path = "kind"
            if not which("kind"):
                kind_path = install_kind(cmd)
            cmd = [kind_path, "create", "cluster", "--name", cluster_name]
            try:
                output = subprocess.check_output(cmd, universal_newlines=True)
                logger.info("%s returned:\n%s", " ".join(cmd), output)
            except subprocess.CalledProcessError as err:
                raise CLIError(err)
        else:
            return
        _install_capz_components(cmd)


def _install_capz_components(cmd):
    os.environ["EXP_MACHINE_POOL"] = "true"
    os.environ["EXP_CLUSTER_RESOURCE_SET"] = "true"
    cmd = ["clusterctl", "init", "--infrastructure", "azure"]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(cmd), output)
    except subprocess.CalledProcessError as err:
        raise CLIError("Can't locate a Kubernetes cluster") from err


def create_management_cluster(cmd):
    # TODO: add user confirmation
    check_preqreqs(cmd)

    cmd = ["clusterctl", "init", "--infrastructure", "azure"]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(cmd), output)
    except subprocess.CalledProcessError as err:
        raise CLIError("Can't locate a Kubernetes cluster") from err


def delete_management_cluster(cmd):  # , yes=False):
    # TODO: add user confirmation
    cmd = ["clusterctl", "delete", "--all",
           "--include-crd", "--include-namespace"]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(cmd), output)
    except subprocess.CalledProcessError as err:
        raise CLIError(err)
    namespaces = [
        "capi-kubeadm-bootstrap-system",
        "capi-kubeadm-control-plane-system",
        "capi-system",
        "capi-webhook-system",
        "capz-system",
        "cert-manager",
    ]
    cmd = ["kubectl", "delete", "namespace", "--ignore-not-found"] + namespaces
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(cmd), output)
    except subprocess.CalledProcessError as err:
        raise CLIError(err)


def move_management_cluster(cmd):
    raise NotImplementedError


def show_management_cluster(_cmd, yes=False):
    # TODO: check to see if a management cluster is specified in the config
    config = get_default_cli().config
    # Config can also be set by the AZURE_CAPI_KUBECONFIG environment variable.
    kubeconfig = config.get("capi", "kubeconfig",
                            fallback=os.environ.get("KUBECONFIG"))
    if not kubeconfig:
        raise CLIError("no kubeconfig")
    # make a $HOME/.azure/capi directory for storing cluster configurations
    path = os.path.join(get_config_dir(), "capi")
    if not os.path.exists(path):
        os.makedirs(path)
    # TODO: if not
    command = ["kubectl", "config", "get-contexts",
               "--no-headers", "--output", "name"]
    try:
        output = subprocess.check_output(command, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(command), output)
        contexts = output.splitlines()
        logger.info(contexts)
    except subprocess.CalledProcessError as err:
        raise CLIError(err)

    msg = path + "ok"
    if not yes and prompt_y_n(msg, default="n"):
        logger.info("yes")
    # TODO: echo details of the management cluster in all output formats


def update_management_cluster(cmd):
    # Check for local prerequisites
    check_preqreqs(cmd)
    cmd = [
        "clusterctl",
        "upgrade",
        "apply",
        "--management-group",
        "capi-system/cluster-api",
        "--contract",
        "v1alpha3",
    ]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
        logger.info("%s returned:\n%s", " ".join(cmd), output)
    except subprocess.CalledProcessError as err:
        raise CLIError(err)


def create_workload_cluster(  # pylint: disable=unused-argument,too-many-arguments,too-many-locals
        cmd,
        resource_group_name,
        capi_name,
        location=None,
        control_plane_machine_type=os.environ.get(
            "AZURE_CONTROL_PLANE_MACHINE_TYPE"),
        control_plane_machine_count=os.environ.get(
            "AZURE_CONTROL_PLANE_MACHINE_COUNT", 3),
        node_machine_type=os.environ.get("AZURE_NODE_MACHINE_TYPE"),
        node_machine_count=os.environ.get("AZURE_NODE_MACHINE_COUNT", 3),
        kubernetes_version=os.environ.get("AZURE_KUBERNETES_VERSION", "1.20.2"),
        # azure_cloud=os.environ.get("AZURE_ENVIRONMENT", "AzurePublicCloud"),
        subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID"),
        ssh_public_key=os.environ.get("AZURE_SSH_PUBLIC_KEY_B64", ""),
        vnet_name=None,
        yes=False):
    init_environment(cmd)

    # Prompt to create resource group if it doesn't exist
    from azure.cli.core.commands.client_factory import get_mgmt_service_client
    from azure.cli.core.profiles import ResourceType

    resource_client = get_mgmt_service_client(
        cmd.cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES)
    if not resource_client.resource_groups.check_existence(resource_group_name):
        logger.warning("Couldn't find the specified resource group.")
        if not location:
            raise CLIError(
                'Please specify a location so a resource group can be created.')
        create = yes
        if not create:
            msg = 'Do you want to create a new resource group named "{}" in Azure\'s {} region?'.format(
                resource_group_name, location)
            create = prompt_y_n(msg, default="n")
        if create:
            rg_model = resource_client.models().ResourceGroup
            # TODO: add tags to resource group?
            parameters = rg_model(location=location)
            output = resource_client.resource_groups.create_or_update(
                resource_group_name, parameters)
            logger.info(output)
            logger.warning("Created resource group %s in %s.", resource_group_name, location)
    # Check for general prerequisites
    # init_environment(cmd)
    # Identify or create a Kubernetes v1.16+ management cluster
    find_management_cluster_retry(cmd.cli_ctx)

    # Generate the cluster configuration
    env = Environment(loader=PackageLoader(
        __name__, "templates"), auto_reload=False)
    logger.info("Available templates: %s", env.list_templates())
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
        "KUBERNETES_VERSION": kubernetes_version,
    }
    manifest = template.render(args)

    # TODO: Some CAPZ options need to be set as env vars, not clusterctl arguments.
    # os.environ.update(
    #     {
    #         "AZURE_CONTROL_PLANE_MACHINE_TYPE": control_plane_machine_type,
    #         "AZURE_NODE_MACHINE_TYPE": node_machine_type,
    #         "AZURE_LOCATION": location,
    #         "AZURE_ENVIRONMENT": azure_cloud,
    #     }
    # )
    filename = capi_name + ".yaml"
    with open(filename, "w") as manifest_file:
        manifest_file.write(manifest)
    logger.warning("wrote manifest file to %s", filename)

    msg = 'Do you want to create this Kubernetes cluster "{}" in the Azure resource group "{}"?'
    if prompt_y_n(msg, default="n"):
        # Apply the cluster configuration
        cmd = ["kubectl", "apply", "-f", filename]
        try:
            output = subprocess.check_output(cmd, universal_newlines=True)
            logger.info("`{}` returned:\n{}".format(" ".join(cmd), output))
        except subprocess.CalledProcessError as err:
            raise CLIError(err)
        # TODO: create RG for user with AAD Pod ID scoped to it


def delete_workload_cluster(cmd):
    raise UnimplementedError


def list_workload_clusters(cmd):
    raise UnimplementedError


def update_workload_cluster(cmd):
    raise UnimplementedError


def check_preqreqs(cmd, install=False):
    # Install kubectl
    if not which("kubectl") and install:
        install_kubectl(cmd)

    # Install clusterctl
    if not which("clusterctl") and install:
        install_clusterctl(cmd)

    # Check for required environment variables
    # TODO: remove this when AAD Pod Identity becomes the default
    for var in ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID"]:
        check_environment_var(var)


def check_environment_var(var):
    var_b64 = var + "_B64"
    val = os.environ.get(var_b64)
    if val:
        logger.info("Found environment variable %s", var_b64)
    else:
        try:
            val = os.environ[var]
        except KeyError as err:
            raise CLIError("Required environment variable {} was not found.".format(err))
        # Set the base64-encoded variable as a convenience
        val = base64.b64encode(val.encode("utf-8")).decode("ascii")
        os.environ[var_b64] = val
        logger.info("Set environment variable %s from %s", var_b64, var)


def find_management_cluster_retry(cli_ctx, delay=3):
    hook = cli_ctx.get_progress_controller(True)
    hook.add(message='Waiting for CAPI components to be running',
             value=0, total_val=1.0)
    logger.info('Waiting for CAPI components to be running')
    for i in range(0, 10):
        hook.add(message='Waiting for CAPI components to be running',
                 value=0.1 * i, total_val=1.0)
        try:
            find_management_cluster()
            break
        except CLIError:
            time.sleep(delay + delay * i)
    else:
        return False
    hook.add(message='CAPI components are running', value=1.0, total_val=1.0)
    logger.info('CAPI components are running')
    return True


def find_management_cluster():
    cmd = ["kubectl", "cluster-info"]
    match = check_cmd(cmd, r"Kubernetes control plane.*?is running")
    if match is None:
        raise CLIError("No accessible Kubernetes cluster found")
    cmd = ["kubectl", "get", "pods", "--namespace", "capz-system"]
    try:
        match = check_cmd(cmd, r"capz-controller-manager-.+?Running")
        if match is None:
            raise CLIError("No CAPZ installation found")
    except subprocess.CalledProcessError as err:
        logger.error(err)


def check_cmd(cmd, regexp=None):
    output = subprocess.check_output(cmd, universal_newlines=True)
    logger.info("%s returned:\n%s", " ".join(cmd), output)
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
        raise CLIError(
            'The clusterctl binary is not available for "{}"'.format(system))

    # ensure installation directory exists
    if install_location is None:
        install_location = _get_default_install_location("clusterctl")
    install_dir, cli = os.path.dirname(install_location), os.path.basename(
        install_location
    )
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    logger.warning('Downloading client to "%s" from "%s"',
                   install_location, file_url)
    try:
        _urlretrieve(file_url, install_location)
        perms = (
            os.stat(install_location).st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )
        os.chmod(install_location, perms)
    except IOError as ex:
        raise CLIError(
            "Connection error while attempting to download client ({})".format(
                ex)
        )

    logger.warning(
        "Please ensure that %s is in your search PATH, so the `%s` command can be found.",
        install_dir,
        cli,
    )


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
        raise CLIError('System "{}" is not supported by kind.'.format(system))

    logger.warning('Downloading client to "%s" from "%s"',
                   install_location, file_url)
    try:
        _urlretrieve(file_url, install_location)
        os.chmod(
            install_location,
            os.stat(install_location).st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH,
        )
    except IOError as ex:
        raise CLIError(
            "Connection error while attempting to download client ({})".format(
                ex)
        )

    if system == "Windows":
        # be verbose, as the install_location likely not in Windows's search PATHs
        env_paths = os.environ["PATH"].split(";")
        found = next(
            (x for x in env_paths if x.lower().rstrip("\\") == install_dir.lower()),
            None,
        )
        if not found:
            # pylint: disable=logging-format-interpolation
            logger.warning(
                'Please add "{0}" to your search PATH so the `{1}` can be found. 2 options: \n'
                '    1. Run "set PATH=%PATH%;{0}" or "$env:path += \'{0}\'" for PowerShell. '
                "This is good for the current command session.\n"
                "    2. Update system PATH environment variable by following "
                '"Control Panel->System->Advanced->Environment Variables", and re-open the command window. '
                "You only need to do it once".format(install_dir, cli)
            )
    else:
        logger.warning(
            "Please ensure that %s is in your search PATH, so the `%s` command can be found.",
            install_dir,
            cli,
        )
    return install_location


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
        context = _ssl_context()
        version = urlopen(source_url + "/stable.txt", context=context).read()
        client_version = version.decode("UTF-8").strip()
    else:
        client_version = "v%s" % client_version

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
        raise CLIError(
            "Proxy server ({}) does not exist on the cluster.".format(system)
        )

    logger.warning('Downloading client to "%s" from "%s"',
                   install_location, file_url)
    try:
        _urlretrieve(file_url, install_location)
        os.chmod(
            install_location,
            os.stat(install_location).st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH,
        )
    except IOError as ex:
        raise CLIError(
            "Connection error while attempting to download client ({})".format(
                ex)
        )

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
                'Please add "{0}" to your search PATH so the `{1}` can be found. 2 options: \n'
                '    1. Run "set PATH=%PATH%;{0}" or "$env:path += \'{0}\'" for PowerShell. '
                "This is good for the current command session.\n"
                "    2. Update system PATH environment variable by following "
                '"Control Panel->System->Advanced->Environment Variables", and re-open the command window. '
                "You only need to do it once".format(install_dir, cli)
            )
    else:
        logger.warning(
            "Please ensure that %s is in your search PATH, so the `%s` command can be found.",
            install_dir,
            cli,
        )


def _ssl_context():
    if sys.version_info < (3, 4) or (in_cloud_console() and platform.system() == "Windows"):
        try:
            # added in python 2.7.13 and 3.6
            return ssl.SSLContext(ssl.PROTOCOL_TLS)
        except AttributeError:
            return ssl.SSLContext(ssl.PROTOCOL_TLSv1)

    return ssl.create_default_context()


def _urlretrieve(url, filename):
    req = urlopen(url, context=_ssl_context())
    with open(filename, "wb") as out:
        out.write(req.read())
