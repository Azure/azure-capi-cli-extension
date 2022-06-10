# Azure CAPI CLI Usage

See [Kubernetes Cluster API Provider Azure](https://capz.sigs.k8s.io/) for more information.

### `az capi create`

Create a workload cluster.

|Option|Type|Description|
|------|----|-----------|
|**--name -n** [Required]|`String`|Name of the CAPI Kubernetes cluster.|
|**--bootstrap-commands**|`String`| YAML file with user-defined VM bootstrap commands.|
|**--control-plane-machine-count**|`Integer`|Control Plane Machine Count|
|**--control-plane-machine-type**|`String`|Control Plane Machine Type|
|**--ephemeral-disks -e**|`Bool`|Use ephemeral disks.|
|**--kubernetes-version -k**|`String`|Version of Kubernetes to use.|
|**--location**|`String`|Location. Values from: `az account list-locations`. You can configure the default location using `az configure --defaults location=<location>`. If not specified, the location of the `--resource-group` will be used. Required if `--resource-group` is not specified or does not yet exist.|
|**--machinepool -m**|`String`|Use experimental MachinePools instead of MachineDeployments.|
|**--management-cluster-name**|`String`|Name for management cluster.|
|**--management-cluster-resource-group-name -mg**|`String`|Resource group name of management cluster.|
|**--node-machine-count**|`Integer`| Node Machine Count|
|**--node-machine-type**|`String`| Node Machine Type|
|**----pivot**|`Bool`| Move provider and CAPI resources to workload cluster. Learn more about [Pivot](https://cluster-api.sigs.k8s.io/clusterctl/commands/move.html).|
|**--resource-group -g**|`String`|Name of resource group. You can configure the default group using `az configure --defaults group=<name>`. If not specified, the value of `--name` will be used.|
|**--ssh-public-key**|`String`|Public key contents to install on node VMs for SSH access.|
|**--template**|`String`|User-defined template to create a workload cluster. Accepts a URL or file.|
|**--vnet-name**|`String`| Name of the Virtual Network to create.|
|**--windows -w**|`Bool`|For built-in templates: Include a Windows node pool. For custom templates [`--template`]: Deploy Windows CNI.|
|**--yes -y**|`Bool`| Do not prompt for confirmation|

#### `--bootstrap-commands` usage:

These commands are implemented via Cluster API bootstrap provider kubeadm. This provider is responsible for generating a cloud-init script to turn a machine into a kubernetes node. The commands run before and after kubeadm init/join on each VM. To learn more, visit: [Cluster API bootstrap provider kubeadm](https://cluster-api.sigs.k8s.io/tasks/kubeadm-bootstrap.html?#additional-features).

`az capi create --bootstrap-commands <path-to-yaml-file>`

The file should contain commands in this YAML format:
```yaml
---
preBootstrapCommands:
- touch /tmp/pre-bootstrap-command-was-here
postBootstrapCommands:
- touch /tmp/post-bootstrap-command-was-here
```
Alternative YAML format for a single pre and post command:
```yaml
---
postBootstrapCommands: touch /tmp/pre-bootstrap-command-was-here
preBootstrapCommands: touch /tmp/post-bootstrap-command-was-here
```

#### `--template` usage:

User-defined template to create a workload cluster. Accepts a URL or file.

`az capi create --template <URL-template>`
`az capi create --template <path-to-cluster-template-file>`

See [CAPZ templates](https://github.com/kubernetes-sigs/cluster-api-provider-azure/tree/main/templates) for a start refence for cluster custom templates

### `az capi delete`

Delete a workload cluster.

|Option|Type|Description|
|------|----|-----------|
|**--name -n** [Required]|`String`|Name of the CAPI Kubernetes cluster.|
|**--resource-group -g**|`String`|Name of resource group. You can configure the default group using `az configure --defaults group=<name>`. If not specified, the value of `--name` will be used.|
|**--yes -y**|`Bool`| Do not prompt for confirmation|

### `az capi list`

List workload clusters.

### `az capi delete`

Show details of a workload cluster.

|Option|Type|Description|
|------|----|-----------|
|**--name -n** [Required]|`String`|Name of the CAPI Kubernetes cluster.|

## Management Subgroup commands 

### `az capi management create`

Create a CAPI management cluster.

|Option|Type|Description|
|------|----|-----------|
|**--cluster-name** |`String`|Name for management cluster.|
|**--location**|`String`|Location. Values from: `az account list-locations`. You can configure the default location using `az configure --defaults location=<location>`. If not specified, the location of the `--resource-group` will be used. Required if `--resource-group` is not specified or does not yet exist.|
|**--resource-group -g**|`String`|Name of resource group. You can configure the default group using `az configure --defaults group=<name>`. If not specified, the value of `--name` will be used.|
|**--yes -y**|`Bool`| Do not prompt for confirmation|

### `az capi management delete`

Delete a CAPI management cluster.

|Option|Type|Description|
|------|----|-----------|
|**--yes -y**|`Bool`| Do not prompt for confirmation|


## Troubleshoot commands
## `az capi install`

Install needed tools for CAPI CLI Extension

|Option|Type|Description|
|------|----|-----------|
|**--all**|`Bool`|Install all needed tools for CAPI CLI Extension|