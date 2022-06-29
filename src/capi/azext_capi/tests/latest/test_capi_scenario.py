# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
from unittest.mock import MagicMock, Mock, patch, ANY

from azure.cli.testsdk.scenario_tests import AllowLargeResponse
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import RequiredArgumentMissingError
from azure.cli.testsdk import (ScenarioTest, ResourceGroupPreparer)
from azure.core.exceptions import ResourceNotFoundError as ResourceNotFoundException
from knack.prompting import NoTTYException
from msrestazure.azure_exceptions import CloudError

TEST_DIR = os.path.abspath(os.path.join(os.path.abspath(__file__), '..'))


class CapiScenarioTest(ScenarioTest):

    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_create(self, mock_def):
        mock_client = MagicMock()
        mock_client.get.side_effect = ResourceNotFoundException("The resource group could not be found.")
        # Test that error is raised if no args are passed
        with patch('azext_capi._client_factory.cf_resource_groups') as cf_resource_groups:
            cf_resource_groups.return_value = mock_client
            with self.assertRaises(RequiredArgumentMissingError):
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
        # New RG, no --location, AZURE_LOCATION set
        with patch.dict('os.environ', {"AZURE_LOCATION": "westus3"}):
            with patch('azext_capi.custom.check_resource_group') as mock_check_rg:
                with self.assertRaises(NoTTYException):
                    self.cmd('capi create -n myClusterName -g myCluster')
                mock_check_rg.assert_called_with(ANY, ANY, ANY, "westus3")
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
                self.check('items[0].metadata.name', 'default-4377'),
                self.check('items[1].kind', 'Cluster'),
                self.check('items[1].metadata.name', 'testcluster1'),
            ])

            count = len(self.cmd("capi list --output json").get_output_in_json())
            self.assertEqual(count, 4)  # "apiVersion", "items", "kind", and "metadata".

            tsv = self.cmd("capi list --output tsv").output
            self.assertEqual(tsv, '2022-05-27T20:53:08Z\tdefault-4377\tdefault\tProvisioned\n2022-05-27T20:58:06Z\ttestcluster1\tdefault\tProvisioned\n')

            self.assertEqual(mock.call_count, 3)

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

            tsv = self.cmd("capi show --name testcluster1 --output tsv").output
            self.assertEqual(tsv, '2022-05-27T20:58:06Z\ttestcluster1\tdefault\tProvisioned\n')

            self.assertEqual(mock.call_count, 3)

    @patch('azext_capi.custom.kubectl_helpers.find_cluster_in_current_context', return_value="testcluster1")
    @patch('azext_capi.custom.is_self_managed_cluster', return_value=False)
    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_delete(self, mock_def, mock_is_self_managed, find_cluster_mock):
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

    @patch('azext_capi.custom.delete_aks_cluster')
    @patch('azext_capi.custom.delete_kind_cluster_from_current_context')
    @patch('azext_capi.custom.has_kind_prefix')
    @patch('azext_capi.custom.kubectl_helpers.find_cluster_in_current_context')
    @patch('azext_capi.custom.exit_if_no_management_cluster')
    def test_capi_management_delete(self, mock_def, find_cluster_mock, kind_pref_mock, delete_kind_mock, delete_aks_mock):
        # Test (indirectly) that user is prompted for confirmation by default
        with self.assertRaises(NoTTYException):
            self.cmd('capi management delete')

        # Test that --yes skips confirmation and the management cluster components are deleted
            self.cmd("capi management delete -y", checks=[
                self.is_empty(),
            ])

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
      "apiVersion": "cluster.x-k8s.io/v1beta1",
      "kind": "Cluster",
      "metadata": {
        "annotations": {
          "kubectl.kubernetes.io/last-applied-configuration": ""
        },
        "creationTimestamp": "2022-05-27T20:53:08Z",
        "finalizers": [
          "cluster.cluster.x-k8s.io"
        ],
        "generation": 2,
        "labels": {
          "cni": "calico"
        },
        "name": "default-4377",
        "namespace": "default",
        "resourceVersion": "40534",
        "uid": "11b0a41f-e10b-4919-917f-62d9fd58a14d"
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
          "host": "default-4377-c4b964c2.eastus.cloudapp.azure.com",
          "port": 6443
        },
        "controlPlaneRef": {
          "apiVersion": "controlplane.cluster.x-k8s.io/v1beta1",
          "kind": "KubeadmControlPlane",
          "name": "default-4377-control-plane",
          "namespace": "default"
        },
        "infrastructureRef": {
          "apiVersion": "infrastructure.cluster.x-k8s.io/v1beta1",
          "kind": "AzureCluster",
          "name": "default-4377",
          "namespace": "default"
        }
      },
      "status": {
        "conditions": [
          {
            "lastTransitionTime": "2022-05-27T20:57:55Z",
            "status": "True",
            "type": "Ready"
          },
          {
            "lastTransitionTime": "2022-05-27T20:57:29Z",
            "status": "True",
            "type": "ControlPlaneInitialized"
          },
          {
            "lastTransitionTime": "2022-05-27T20:57:55Z",
            "status": "True",
            "type": "ControlPlaneReady"
          },
          {
            "lastTransitionTime": "2022-05-27T20:55:29Z",
            "status": "True",
            "type": "InfrastructureReady"
          }
        ],
        "controlPlaneReady": true,
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
      "apiVersion": "cluster.x-k8s.io/v1beta1",
      "kind": "Cluster",
      "metadata": {
        "annotations": {
          "kubectl.kubernetes.io/last-applied-configuration": ""
        },
        "creationTimestamp": "2022-05-27T20:58:06Z",
        "finalizers": [
          "cluster.cluster.x-k8s.io"
        ],
        "generation": 2,
        "labels": {
          "cni": "calico"
        },
        "name": "testcluster1",
        "namespace": "default",
        "resourceVersion": "41760",
        "uid": "d5db70c7-2804-4eb9-b2fc-d65fe7b258a1"
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
          "host": "testcluster1-4ea828b6.westus3.cloudapp.azure.com",
          "port": 6443
        },
        "controlPlaneRef": {
          "apiVersion": "controlplane.cluster.x-k8s.io/v1beta1",
          "kind": "KubeadmControlPlane",
          "name": "testcluster1-control-plane",
          "namespace": "default"
        },
        "infrastructureRef": {
          "apiVersion": "infrastructure.cluster.x-k8s.io/v1beta1",
          "kind": "AzureCluster",
          "name": "testcluster1",
          "namespace": "default"
        }
      },
      "status": {
        "conditions": [
          {
            "lastTransitionTime": "2022-05-27T21:01:47Z",
            "message": "Scaling up control plane to 3 replicas (actual 2)",
            "reason": "ScalingUp",
            "severity": "Warning",
            "status": "False",
            "type": "Ready"
          },
          {
            "lastTransitionTime": "2022-05-27T21:01:39Z",
            "status": "True",
            "type": "ControlPlaneInitialized"
          },
          {
            "lastTransitionTime": "2022-05-27T21:01:47Z",
            "message": "Scaling up control plane to 3 replicas (actual 2)",
            "reason": "ScalingUp",
            "severity": "Warning",
            "status": "False",
            "type": "ControlPlaneReady"
          },
          {
            "lastTransitionTime": "2022-05-27T20:59:37Z",
            "status": "True",
            "type": "InfrastructureReady"
          }
        ],
        "controlPlaneReady": true,
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
  "apiVersion": "cluster.x-k8s.io/v1beta1",
  "kind": "Cluster",
  "metadata": {
    "annotations": {
      "kubectl.kubernetes.io/last-applied-configuration": ""
    },
    "creationTimestamp": "2022-05-27T20:58:06Z",
    "finalizers": [
      "cluster.cluster.x-k8s.io"
    ],
    "generation": 2,
    "labels": {
      "cni": "calico"
    },
    "name": "testcluster1",
    "namespace": "default",
    "resourceVersion": "41760",
    "uid": "d5db70c7-2804-4eb9-b2fc-d65fe7b258a1"
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
      "host": "testcluster1-4ea828b6.westus3.cloudapp.azure.com",
      "port": 6443
    },
    "controlPlaneRef": {
      "apiVersion": "controlplane.cluster.x-k8s.io/v1beta1",
      "kind": "KubeadmControlPlane",
      "name": "testcluster1-control-plane",
      "namespace": "default"
    },
    "infrastructureRef": {
      "apiVersion": "infrastructure.cluster.x-k8s.io/v1beta1",
      "kind": "AzureCluster",
      "name": "testcluster1",
      "namespace": "default"
    }
  },
  "status": {
    "conditions": [
      {
        "lastTransitionTime": "2022-05-27T21:01:47Z",
        "message": "Scaling up control plane to 3 replicas (actual 2)",
        "reason": "ScalingUp",
        "severity": "Warning",
        "status": "False",
        "type": "Ready"
      },
      {
        "lastTransitionTime": "2022-05-27T21:01:39Z",
        "status": "True",
        "type": "ControlPlaneInitialized"
      },
      {
        "lastTransitionTime": "2022-05-27T21:01:47Z",
        "message": "Scaling up control plane to 3 replicas (actual 2)",
        "reason": "ScalingUp",
        "severity": "Warning",
        "status": "False",
        "type": "ControlPlaneReady"
      },
      {
        "lastTransitionTime": "2022-05-27T20:59:37Z",
        "status": "True",
        "type": "InfrastructureReady"
      }
    ],
    "controlPlaneReady": true,
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
}
"""
