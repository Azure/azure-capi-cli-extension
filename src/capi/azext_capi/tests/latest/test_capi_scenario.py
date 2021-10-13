# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from azure_devtools.scenario_tests import AllowLargeResponse
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import RequiredArgumentMissingError
from azure.cli.testsdk import (ScenarioTest, ResourceGroupPreparer)
from knack.prompting import NoTTYException
from msrestazure.azure_exceptions import CloudError


TEST_DIR = os.path.abspath(os.path.join(os.path.abspath(__file__), '..'))


class CapiScenarioTest(ScenarioTest):

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_create(self, mock_def):
        # Test that error is raised if no args are passed
        with self.assertRaises(SystemExit):
            self.cmd('capi create')
        # Test that --name is the only required arg if it already exists
        with patch('azext_capi._client_factory.cf_resource_groups') as cf_resource_groups:
            # If we got to user confirmation (NoTTYException), RG validation succeeded
            with self.assertRaises(NoTTYException):
                self.cmd('capi create -n myCluster')
        # Existing RG which doesn't match --location
        with patch('azext_capi._client_factory.cf_resource_groups') as cf_resource_groups:
            with self.assertRaises(InvalidArgumentValueError):
                self.cmd('capi create -n myCluster -g existingRG --location bogusLocation')
        mock_client = MagicMock()
        mock_client.get.side_effect = CloudError(Mock(response_status=404), "Resource group 'myCluster' could not be found.")
        # New RG, but no --location specified
        with patch('azext_capi._client_factory.cf_resource_groups') as cf_resource_groups:
            cf_resource_groups.return_value = mock_client
            with self.assertRaises(RequiredArgumentMissingError):
                self.cmd('capi create -n myClusterName -g myCluster')
        # New RG, --location specified but no --resource-group name
        with patch('azext_capi._client_factory.cf_resource_groups') as cf_resource_groups:
            cf_resource_groups.return_value = mock_client
            # If we got to user confirmation (NoTTYException), RG validation succeeded
            with self.assertRaises(NoTTYException):
                self.cmd('capi create -n myCluster -l southcentralus')

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_list(self, mock_def):
        with patch('subprocess.check_output') as mock:
            mock.return_value = AZ_CAPI_LIST_JSON
            self.cmd('capi list --output json', checks=[
                self.check('items[0].kind', 'Cluster'),
                self.check('items[0].metadata.name', 'testcluster1'),
                self.check('items[1].kind', 'Cluster'),
                self.check('items[1].metadata.name', 'testcluster2'),
            ])

            count = len(self.cmd("capi list --output json").get_output_in_json())
            self.assertEqual(count, 4)  # "apiVersion", "items", "kind", and "metadata".

            self.assertEqual(mock.call_count, 2)

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_show(self, mock_def):
        # Test that error is raised if no args are passed
        with self.assertRaises(SystemExit):
            self.cmd('capi show')

        with patch('subprocess.check_output') as mock:
            mock.return_value = AZ_CAPI_SHOW_JSON
            self.cmd('capi show --name testcluster1 --output json', checks=[
                self.check('kind', 'Cluster'),
                self.check('metadata.name', 'testcluster1'),
            ])

            count = len(self.cmd("capi show --name testcluster1 --output json").get_output_in_json())
            self.assertEqual(count, 5)  # "apiVersion", "kind", "metadata", "spec", and "status"

            self.assertEqual(mock.call_count, 2)

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_delete(self, mock_def):
        # Test (indirectly) that user is prompted for confirmation by default
        with self.assertRaises(NoTTYException):
            self.cmd('capi delete --name testcluster1')

        # Test that --yes skips confirmation and the cluster is deleted
        with patch('subprocess.check_output') as mock:
            self.cmd("capi delete --name testcluster1 --yes", checks=[
                self.is_empty(),
            ])
            self.assertTrue(mock.called)
            self.assertEqual(mock.call_args[0][0], ["kubectl", "delete", "cluster", "testcluster1"])

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_management_delete(self, mock_def):
        # Test (indirectly) that user is prompted for confirmation by default
        with self.assertRaises(NoTTYException):
            self.cmd('capi management delete')

        # Test that --yes skips confirmation and the management cluster components are deleted
        with patch('subprocess.check_output') as mock:
            self.cmd("capi management delete -y", checks=[
                self.is_empty(),
            ])
            self.assertEqual(mock.call_count, 2)
            self.assertEqual(mock.call_args_list[0][0][0], ["clusterctl", "delete", "--all", "--include-crd", "--include-namespace"])
            self.assertEqual(mock.call_args_list[1][0][0][:4], ["kubectl", "delete", "namespace", "--ignore-not-found"])

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_management_update(self, mock_def):
        # Test (indirectly) that user is prompted for confirmation by default
        with self.assertRaises(NoTTYException):
            self.cmd('capi management update')

        # Test that --yes skips confirmation and the cluster is updated
        with patch('subprocess.check_output') as mock:
            with patch('azext_capi.custom.check_prereqs'):
                self.cmd("capi management update --yes", checks=[
                    self.is_empty(),
                ])
                self.assertEqual(mock.call_count, 1)
                self.assertEqual(mock.call_args_list[0][0][0][:3], ["clusterctl", "upgrade", "apply"])


AZ_CAPI_LIST_JSON = """\
{
  "apiVersion": "v1",
  "items": [
    {
      "apiVersion": "cluster.x-k8s.io/v1alpha3",
      "kind": "Cluster",
      "metadata": {
        "annotations": {
        },
        "creationTimestamp": "2021-03-31T19:18:10Z",
        "finalizers": [
          "cluster.cluster.x-k8s.io"
        ],
        "generation": 2,
        "labels": {
          "cni": "calico"
        },
        "managedFields": [
          {
            "apiVersion": "cluster.x-k8s.io/v1alpha3",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:metadata": {
                "f:annotations": {
                  ".": {},
                  "f:kubectl.kubernetes.io/last-applied-configuration": {}
                },
                "f:labels": {
                  ".": {},
                  "f:cni": {}
                }
              },
              "f:spec": {
                ".": {},
                "f:clusterNetwork": {
                  ".": {},
                  "f:pods": {
                    ".": {},
                    "f:cidrBlocks": {}
                  }
                },
                "f:controlPlaneRef": {
                  ".": {},
                  "f:apiVersion": {},
                  "f:kind": {},
                  "f:name": {}
                },
                "f:infrastructureRef": {
                  ".": {},
                  "f:apiVersion": {},
                  "f:kind": {},
                  "f:name": {}
                }
              }
            },
            "manager": "kubectl-client-side-apply",
            "operation": "Update",
            "time": "2021-03-31T19:18:10Z"
          },
          {
            "apiVersion": "cluster.x-k8s.io/v1alpha3",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:metadata": {
                "f:finalizers": {
                  ".": {},
                  "v:cluster.cluster.x-k8s.io": {}
                }
              },
              "f:spec": {
                "f:controlPlaneEndpoint": {
                  "f:host": {},
                  "f:port": {}
                }
              },
              "f:status": {
                ".": {},
                "f:conditions": {},
                "f:controlPlaneInitialized": {},
                "f:failureDomains": {
                  ".": {},
                  "f:1": {
                    ".": {},
                    "f:controlPlane": {}
                  },
                  "f:2": {
                    ".": {},
                    "f:controlPlane": {}
                  },
                  "f:3": {
                    ".": {},
                    "f:controlPlane": {}
                  }
                },
                "f:infrastructureReady": {},
                "f:observedGeneration": {},
                "f:phase": {}
              }
            },
            "manager": "manager",
            "operation": "Update",
            "time": "2021-03-31T19:20:58Z"
          }
        ],
        "name": "testcluster1",
        "namespace": "default",
        "resourceVersion": "2566",
        "uid": "ab39bad4-569a-4e5d-874b-775525b71785"
      },
      "spec": {
        "clusterNetwork": {
          "pods": {
            "cidrBlocks": [
              "192.168.0.0/16"
            ]
          }
        },
        "controlPlaneEndpoint": {
          "host": "testcluster1-b4de9daa.southcentralus.cloudapp.azure.com",
          "port": 6443
        },
        "controlPlaneRef": {
          "apiVersion": "controlplane.cluster.x-k8s.io/v1alpha3",
          "kind": "KubeadmControlPlane",
          "name": "testcluster1-control-plane",
          "namespace": "default"
        },
        "infrastructureRef": {
          "apiVersion": "infrastructure.cluster.x-k8s.io/v1alpha3",
          "kind": "AzureCluster",
          "name": "testcluster1",
          "namespace": "default"
        }
      },
      "status": {
        "conditions": [
          {
            "lastTransitionTime": "2021-03-31T19:21:53Z",
            "status": "True",
            "type": "Ready"
          },
          {
            "lastTransitionTime": "2021-03-31T19:21:53Z",
            "status": "True",
            "type": "ControlPlaneReady"
          },
          {
            "lastTransitionTime": "2021-03-31T19:18:53Z",
            "status": "True",
            "type": "InfrastructureReady"
          }
        ],
        "controlPlaneInitialized": true,
        "failureDomains": {
          "1": {
            "controlPlane": true
          },
          "2": {
            "controlPlane": true
          },
          "3": {
            "controlPlane": true
          }
        },
        "infrastructureReady": true,
        "observedGeneration": 2,
        "phase": "Provisioned"
      }
    },
    {
      "apiVersion": "cluster.x-k8s.io/v1alpha3",
      "kind": "Cluster",
      "metadata": {
        "annotations": {
        },
        "creationTimestamp": "2021-03-31T19:52:29Z",
        "finalizers": [
          "cluster.cluster.x-k8s.io"
        ],
        "generation": 1,
        "labels": {
          "cni": "calico"
        },
        "managedFields": [
          {
            "apiVersion": "cluster.x-k8s.io/v1alpha3",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:metadata": {
                "f:annotations": {
                  ".": {},
                  "f:kubectl.kubernetes.io/last-applied-configuration": {}
                },
                "f:labels": {
                  ".": {},
                  "f:cni": {}
                }
              },
              "f:spec": {
                ".": {},
                "f:clusterNetwork": {
                  ".": {},
                  "f:pods": {
                    ".": {},
                    "f:cidrBlocks": {}
                  }
                },
                "f:controlPlaneRef": {
                  ".": {},
                  "f:apiVersion": {},
                  "f:kind": {},
                  "f:name": {}
                },
                "f:infrastructureRef": {
                  ".": {},
                  "f:apiVersion": {},
                  "f:kind": {},
                  "f:name": {}
                }
              }
            },
            "manager": "kubectl-client-side-apply",
            "operation": "Update",
            "time": "2021-03-31T19:52:29Z"
          },
          {
            "apiVersion": "cluster.x-k8s.io/v1alpha3",
            "fieldsType": "FieldsV1",
            "fieldsV1": {
              "f:metadata": {
                "f:finalizers": {
                  ".": {},
                  "v:cluster.cluster.x-k8s.io": {}
                }
              },
              "f:status": {
                ".": {},
                "f:conditions": {},
                "f:observedGeneration": {},
                "f:phase": {}
              }
            },
            "manager": "manager",
            "operation": "Update",
            "time": "2021-03-31T19:52:29Z"
          }
        ],
        "name": "testcluster2",
        "namespace": "default",
        "resourceVersion": "10362",
        "uid": "22444cab-c63b-4593-a2db-00ff2bbfe605"
      },
      "spec": {
        "clusterNetwork": {
          "pods": {
            "cidrBlocks": [
              "192.168.0.0/16"
            ]
          }
        },
        "controlPlaneEndpoint": {
          "host": "",
          "port": 0
        },
        "controlPlaneRef": {
          "apiVersion": "controlplane.cluster.x-k8s.io/v1alpha3",
          "kind": "KubeadmControlPlane",
          "name": "testcluster2-control-plane",
          "namespace": "default"
        },
        "infrastructureRef": {
          "apiVersion": "infrastructure.cluster.x-k8s.io/v1alpha3",
          "kind": "AzureCluster",
          "name": "testcluster2",
          "namespace": "default"
        }
      },
      "status": {
        "conditions": [
          {
            "lastTransitionTime": "2021-03-31T19:52:29Z",
            "reason": "WaitingForControlPlane",
            "severity": "Info",
            "status": "False",
            "type": "Ready"
          },
          {
            "lastTransitionTime": "2021-03-31T19:52:29Z",
            "reason": "WaitingForControlPlane",
            "severity": "Info",
            "status": "False",
            "type": "ControlPlaneReady"
          },
          {
            "lastTransitionTime": "2021-03-31T19:52:29Z",
            "reason": "WaitingForInfrastructure",
            "severity": "Info",
            "status": "False",
            "type": "InfrastructureReady"
          }
        ],
        "observedGeneration": 1,
        "phase": "Provisioning"
      }
    }
  ],
  "kind": "List",
  "metadata": {
    "resourceVersion": "",
    "selfLink": ""
  }
}
"""

AZ_CAPI_SHOW_JSON = """\
{
  "apiVersion": "cluster.x-k8s.io/v1alpha3",
  "kind": "Cluster",
  "metadata": {
    "annotations": {
      "kubectl.kubernetes.io/last-applied-configuration": "{\\"apiVersion\\":\\"cluster.x-k8s.io/v1alpha3\\",\\"kind\\":\\"Cluster\\",\\"metadata\\":{\\"annotations\\":{},\\"labels\\":{\\"cni\\":\\"calico\\"},\\"name\\":\\"testcluster1\\",\\"namespace\\":\\"default\\"},\\"spec\\":{\\"clusterNetwork\\":{\\"pods\\":{\\"cidrBlocks\\":[\\"192.168.0.0/16\\"]}},\\"controlPlaneRef\\":{\\"apiVersion\\":\\"controlplane.cluster.x-k8s.io/v1alpha3\\",\\"kind\\":\\"KubeadmControlPlane\\",\\"name\\":\\"testcluster1-control-plane\\"},\\"infrastructureRef\\":{\\"apiVersion\\":\\"infrastructure.cluster.x-k8s.io/v1alpha3\\",\\"kind\\":\\"AzureCluster\\",\\"name\\":\\"testcluster1\\"}}}\\n"
    },
    "creationTimestamp": "2021-04-05T15:34:38Z",
    "finalizers": [
      "cluster.cluster.x-k8s.io"
    ],
    "generation": 1,
    "labels": {
      "cni": "calico"
    },
    "managedFields": [
      {
        "apiVersion": "cluster.x-k8s.io/v1alpha3",
        "fieldsType": "FieldsV1",
        "fieldsV1": {
          "f:metadata": {
            "f:annotations": {
              ".": {},
              "f:kubectl.kubernetes.io/last-applied-configuration": {}
            },
            "f:labels": {
              ".": {},
              "f:cni": {}
            }
          },
          "f:spec": {
            ".": {},
            "f:clusterNetwork": {
              ".": {},
              "f:pods": {
                ".": {},
                "f:cidrBlocks": {}
              }
            },
            "f:controlPlaneRef": {
              ".": {},
              "f:apiVersion": {},
              "f:kind": {},
              "f:name": {}
            },
            "f:infrastructureRef": {
              ".": {},
              "f:apiVersion": {},
              "f:kind": {},
              "f:name": {}
            }
          }
        },
        "manager": "kubectl-client-side-apply",
        "operation": "Update",
        "time": "2021-04-05T15:34:38Z"
      },
      {
        "apiVersion": "cluster.x-k8s.io/v1alpha3",
        "fieldsType": "FieldsV1",
        "fieldsV1": {
          "f:metadata": {
            "f:finalizers": {
              ".": {},
              "v:\\"cluster.cluster.x-k8s.io\\"": {}
            }
          },
          "f:status": {
            ".": {},
            "f:conditions": {},
            "f:observedGeneration": {},
            "f:phase": {}
          }
        },
        "manager": "manager",
        "operation": "Update",
        "time": "2021-04-05T15:34:38Z"
      }
    ],
    "name": "testcluster1",
    "namespace": "default",
    "resourceVersion": "310437",
    "uid": "c6cac420-e480-4b05-95fe-e46e0e0926db"
  },
  "spec": {
    "clusterNetwork": {
      "pods": {
        "cidrBlocks": [
          "192.168.0.0/16"
        ]
      }
    },
    "controlPlaneEndpoint": {
      "host": "",
      "port": 0
    },
    "controlPlaneRef": {
      "apiVersion": "controlplane.cluster.x-k8s.io/v1alpha3",
      "kind": "KubeadmControlPlane",
      "name": "testcluster1-control-plane",
      "namespace": "default"
    },
    "infrastructureRef": {
      "apiVersion": "infrastructure.cluster.x-k8s.io/v1alpha3",
      "kind": "AzureCluster",
      "name": "testcluster1",
      "namespace": "default"
    }
  },
  "status": {
    "conditions": [
      {
        "lastTransitionTime": "2021-04-05T15:34:40Z",
        "reason": "WaitingForControlPlane",
        "severity": "Info",
        "status": "False",
        "type": "Ready"
      },
      {
        "lastTransitionTime": "2021-04-05T15:34:40Z",
        "reason": "WaitingForControlPlane",
        "severity": "Info",
        "status": "False",
        "type": "ControlPlaneReady"
      },
      {
        "lastTransitionTime": "2021-04-05T15:34:38Z",
        "reason": "WaitingForInfrastructure",
        "severity": "Info",
        "status": "False",
        "type": "InfrastructureReady"
      }
    ],
    "observedGeneration": 1,
    "phase": "Provisioning"
  }
}
"""
