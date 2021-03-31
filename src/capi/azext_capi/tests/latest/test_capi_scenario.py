# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import unittest
from unittest.mock import MagicMock, patch

from azure_devtools.scenario_tests import AllowLargeResponse
from azure.cli.testsdk import (ScenarioTest, ResourceGroupPreparer)


TEST_DIR = os.path.abspath(os.path.join(os.path.abspath(__file__), '..'))


class CapiScenarioTest(ScenarioTest):

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_list(self, mock_def):

        with patch('subprocess.check_output') as mock:
            mock.return_value = AZ_CAPI_SHOW_JSON
            self.cmd('capi list --output json', checks=[
                self.check('items[0].kind', 'Cluster'),
                self.check('items[0].metadata.name', 'testcluster1'),
                self.check('items[1].kind', 'Cluster'),
                self.check('items[1].metadata.name', 'testcluster2'),
            ])

            count = len(self.cmd("capi list").get_output_in_json())
            self.assertEqual(count, 4)  # "apiVersion", "items", kind", and "metadata".

            self.assertEqual(mock.call_count, 2)

        # self.cmd('capi create -g {rg} -n {name} --tags foo=doo', checks=[
        #     self.check('tags.foo', 'doo'),
        #     self.check('name', '{name}')
        # ])
        # self.cmd('capi update -g {rg} -n {name} --tags foo=boo', checks=[
        #     self.check('tags.foo', 'boo')
        # ])
        # count = len(self.cmd('capi list').get_output_in_json())
        # self.cmd('capi show - {rg} -n {name}', checks=[
        #     self.check('name', '{name}'),
        #     self.check('resourceGroup', '{rg}'),
        #     self.check('tags.foo', 'boo')
        # ])
        # self.cmd('capi delete -g {rg} -n {name}')
        # final_count = len(self.cmd('capi list').get_output_in_json())
        # self.assertTrue(final_count, count - 1)


AZ_CAPI_SHOW_JSON = """\
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
