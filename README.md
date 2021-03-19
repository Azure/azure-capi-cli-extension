# Kubernetes Cluster API extension for Azure CLI

![Python](https://img.shields.io/pypi/pyversions/azure-cli.svg?maxAge=2592000)
![.github/workflows/build.yml](https://github.com/Azure/azure-capi-cli-extension/workflows/.github/workflows/build.yml/badge.svg)

The **Kubernetes Cluster API extension for Azure CLI** helps you create, evolve, and maintain
[Kubernetes](https://kubernetes.io/) clusters on Azure in a familiar, declarative way. Add this
extension to your Azure CLI to harness the power and flexibility of
[Cluster API](https://cluster-api.sigs.k8s.io/) (CAPI) in just a few `az capi` commands.

## How to Use

* [Install `az`](https://docs.microsoft.com/cli/azure/install-azure-cli), the command-line
  interface to the Microsoft Azure cloud
* Use `az extension add` with
  the [latest release](https://github.com/Azure/azure-capi-cli-extension/releases)
* Run `az capi -h` to get an overview of the commands available to you

## Developer Setup

Developing this Azure CLI extension requires a virtual environment with Python 3.6 or later,
several required libraries, and the `azdev` tool.

You can jump into development right now on the web or on your workstation with
[GitHub Codespaces](https://github.com/features/codespaces), or you can set up a local environment.

### GitHub Codespaces

From the [GitHub homepage](https://github.com/Azure/azure-capi-cli-extension) for this project,
click the big green "Code" button and choose "Open with Codespaces." After some time to prepare the
environment, you'll be presented with the web-based version of Visual Studio Code with this
project's source code ready to hack on.

You can also use codespaces for local development. After opening the codespace as described
above, click the "Open in Visual Studio Code" button on the environment preparation screen.

**NOTE:** when the Codespace runs for the first time, the `create-dev-env.sh` script will still be
running. After a few minutes, the virtual environment will be configured and ready.

### Local Environment

Create a [virtual environment](https://docs.python.org/3/tutorial/venv.html) for Python 3.6 or
later, activate it, install required libraries, and tell the `azdev` tool about our
"capi" extension:

```shell
./create-dev-env.sh
```

The script may take several minutes to complete, so please be patient.

### Linting and Testing

You can lint and test your code with these commands:

```shell
source ./env/bin/activate

azdev style
azdev test
```

### Submitting Pull Requests

To add a feature or change an existing one, please begin by submitting a markdown document
that briefly describes your proposal. This will allow others to review and suggest improvements
before you move forward with implementation.

Since this extension hopes to become an official one and eventually to merge upstream,
pull requests should follow the
[azure-cli guidelines](https://github.com/Azure/azure-cli/tree/dev/doc/authoring_command_modules#submitting-pull-requests).

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
