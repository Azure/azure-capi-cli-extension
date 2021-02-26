# Kubernetes Cluster API extension for Azure CLI

![Python](https://img.shields.io/pypi/pyversions/azure-cli.svg?maxAge=2592000)
![.github/workflows/build.yml](https://github.com/Azure/azure-capi-cli-extension/workflows/.github/workflows/build.yml/badge.svg)

The **Kubernetes Cluster API extension for Azure CLI** helps you create, evolve, and maintain
[Kubernetes](https://kubernetes.io/) clusters on Azure in a familiar, declarative way. Add this extension
to your Azure CLI to harness the power and flexibility of [Cluster API](https://cluster-api.sigs.k8s.io/)
(CAPI) in just a few `az capi` commands.

## How to Use

* [Install `az`](https://docs.microsoft.com/cli/azure/install-azure-cli), the command-line interface to the Microsoft Azure cloud
* Use `az extension add` with the [latest release](https://github.com/Azure/azure-capi-cli-extension/releases)

## Developer Setup

Create a [virtual environment](https://docs.python.org/3/tutorial/venv.html) for Python 3.6 or later
and activate it for all development and testing on this project:

```shell
python3 -m venv env
source env/bin/activate

python -m pip install -U pip
python -m pip install -r requirements.txt
azdev setup --repo . --ext capi --verbose
```

The `azdev setup` command may take several minutes to complete, so please be patient.

You can lint your code with these commands in the virtual environment:

```shell
pylint --disable=fixme src
flake8 src
```

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
