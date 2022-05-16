# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=missing-docstring

import os
import platform
import stat

from azure.cli.core.azclierror import FileOperationError
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import ValidationError
from knack.prompting import prompt_y_n
from six.moves.urllib.request import urlopen  # pylint: disable=import-error

from azext_capi.helpers.network import ssl_context, urlretrieve
from azext_capi._params import _get_default_install_location
from azext_capi.helpers.logger import logger
from azext_capi.helpers.spinner import Spinner


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


def check_clusterctl(cmd, install=False):
    check_binary(cmd, "clusterctl", install_clusterctl, install)


def check_kind(cmd, install=False):
    check_binary(cmd, "kind", install_kind, install)


def check_kubectl(cmd, install=False):
    check_binary(cmd, "kubectl", install_kubectl, install)


def check_binary(cmd, binary_name, install_binary_method, install=False):
    if not which(binary_name):
        logger.info(f"{binary_name} was not found.")
        if install or prompt_y_n(f"Download and install {binary_name}?", default="n"):
            with Spinner(cmd, f"Downloading {binary_name}", f"✓ Downloaded {binary_name}"):
                install_binary_method(cmd)


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
