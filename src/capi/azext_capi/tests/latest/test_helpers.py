# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import subprocess
import os
import sys
import tempfile
import unittest
import yaml
from collections import namedtuple
from unittest.mock import patch, Mock

from azure.cli.core.azclierror import UnclassifiedUserFault
from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.azclierror import ResourceNotFoundError

import azext_capi.helpers.network as network
import azext_capi.helpers.generic as generic
from azext_capi.custom import create_resource_group, create_new_management_cluster, management_cluster_components_missing_matching_expressions, get_default_bootstrap_commands, parse_bootstrap_commands_from_file
from azext_capi.helpers.binary import get_arch
from azext_capi.helpers.prompt import get_user_prompt_or_default
from azext_capi.helpers.kubectl import check_kubectl_namespace, find_attribute_in_context, find_kubectl_current_context, find_default_cluster, add_kubeconfig_to_command
from azext_capi.helpers.names import generate_cluster_name
from azext_capi.helpers.os import prep_kube_config
from azext_capi.helpers.run_command import message_variants, run_shell_command, try_command_with_spinner


class TestSSLContextHelper(unittest.TestCase):

    Case = namedtuple('Case', ['major', 'minor', 'cloud_console', 'system'])

    cases = [
        Case(3, 4, False, 'Windows'),
        Case(3, 4, True, 'Windows'),
        Case(3, 4, False, 'Linux'),
        Case(3, 4, True, 'Linux'),
        Case(3, 6, False, 'Windows'),
        Case(3, 6, True, 'Windows'),
        Case(3, 6, False, 'Linux'),
        Case(3, 6, True, 'Linux'),
        Case(3, 9, False, 'Windows'),
        Case(3, 9, True, 'Windows'),
        Case(3, 9, False, 'Linux'),
        Case(3, 9, True, 'Linux'),
    ]

    def test_ssl_context(self):
        for case in self.cases:
            with patch('azure.cli.core.util.in_cloud_console', return_value=case.cloud_console):
                with patch.object(sys, 'version_info', (case.major, case.minor)):
                    with patch('platform.system', return_value=case.system):
                        self.assertTrue(network.ssl_context())


class TestURLRetrieveHelper(unittest.TestCase):

    @patch('azext_capi.helpers.network.urlopen')
    def test_urlretrieve(self, mock_urlopen):
        random_bytes = os.urandom(2048)
        req = mock_urlopen.return_value
        req.read.return_value = random_bytes
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.close()
            network.urlretrieve('https://dummy.url', fp.name)
            self.assertEqual(open(fp.name, 'rb').read(), random_bytes)
            os.unlink(fp.name)


class FindDefaultCluster(unittest.TestCase):

    def setUp(self):
        self.cmd = Mock()
        self.match_output_patch = patch('azext_capi.helpers.kubectl.match_output')
        self.match_output_mock = self.match_output_patch.start()
        self.match_output_mock.return_value = None
        self.addCleanup(self.match_output_patch.stop)

        self.run_shell_command_patch = patch('azext_capi.helpers.kubectl.run_shell_command')
        self.run_shell_command_mock = self.run_shell_command_patch.start()
        self.addCleanup(self.run_shell_command_patch.stop)

    # Test kubernetes cluster is found and running
    def test_found_k8s_cluster_running_state(self):
        self.run_shell_command_mock.return_value = "fake_return"
        self.match_output_mock.return_value = Mock()
        result = find_default_cluster()
        self.match_output_mock.assert_called_once()
        self.assertTrue(result)

    # Test kubernetes cluster is found but not running state matched
    def test_found_cluster_non_running_state(self):
        self.run_shell_command_mock.return_value = "fake_return"
        with self.assertRaises(ResourceNotFoundError):
            find_default_cluster()

    # Test error with command ran
    def test_encouter_error_with_ran_command(self):
        self.run_shell_command_mock.side_effect = subprocess.CalledProcessError(3, ['fakecommand'])
        with self.assertRaises(subprocess.CalledProcessError):
            find_default_cluster()


class CreateNewManagementCluster(unittest.TestCase):

    def setUp(self):
        self.cmd = Mock()
        self.prompt_y_n_patch = patch('azext_capi.custom.prompt_y_n')
        self.prompt_y_n_mock = self.prompt_y_n_patch.start()
        self.addCleanup(self.prompt_y_n_patch.stop)
        self.get_cluster_prompt_patch = patch('azext_capi.custom.get_cluster_name_by_user_prompt')
        self.get_cluster_prompt_mock = self.get_cluster_prompt_patch.start()
        self.addCleanup(self.get_cluster_prompt_patch.stop)
        self.try_cmd_patch = patch('azext_capi.custom.try_command_with_spinner')
        self.try_cmd_mock = self.try_cmd_patch.start()
        self.addCleanup(self.try_cmd_patch.stop)
        self.prompt_list_patch = patch('azext_capi.custom.prompt_choice_list')
        self.prompt_list_mock = self.prompt_list_patch.start()
        self.addCleanup(self.prompt_list_patch.stop)

    # Test exit after user input
    def test_user_choices_exit_option(self):
        self.prompt_list_mock.return_value = 2
        result = create_new_management_cluster(self.cmd)
        self.assertFalse(result)

    # Test create local kind management cluster
    def test_user_choices_kind_option(self):
        self.prompt_list_mock.return_value = 1
        with patch('azext_capi.custom.check_kind'):
            result = create_new_management_cluster(self.cmd)
            self.assertTrue(result)

    # Test create AKS management cluster
    def test_user_choices_aks_option(self):
        self.prompt_list_mock.return_value = 0
        with patch('azext_capi.custom.create_aks_management_cluster'):
            result = create_new_management_cluster(self.cmd)
            self.assertTrue(result)


class RunShellMethod(unittest.TestCase):

    def setUp(self):
        self.command = ["fake-command"]

    # Test run valid command
    @patch('subprocess.check_output')
    def test_run_valid_command(self, check_out_mock):
        run_shell_command(self.command)
        check_out_mock.assert_called_once()

    # Test command is non existing or invalid
    def test_run_invalid_command(self):
        with self.assertRaises(FileNotFoundError):
            run_shell_command(self.command)


class FindKubectlCurrentContext(unittest.TestCase):

    def setUp(self):
        self.context_name = "fake-context"
        self.run_shell_patch = patch('azext_capi.helpers.kubectl.run_shell_command')
        self.run_shell_mock = self.run_shell_patch.start()
        self.run_shell_mock.return_value = None
        self.addCleanup(self.run_shell_patch.stop)

    # Test found current context
    def test_existing_current_context(self):
        self.run_shell_mock.return_value = self.context_name
        result = find_kubectl_current_context()
        self.assertEquals(result, self.context_name)

    # Test found current context with extra space
    def test_return_value_is_sanitized(self):
        self.run_shell_mock.return_value = f"  {self.context_name}  "
        result = find_kubectl_current_context()
        self.assertEquals(result, self.context_name)

    # Test does not found current context
    def test_no_found_current_context(self):
        self.run_shell_mock.return_value = None
        error = subprocess.CalledProcessError(3, ['fakecommand'], output="current-context is not set")
        self.run_shell_mock.side_effect = error
        result = find_kubectl_current_context()
        self.assertIsNone(result)


class FindAttributeInContext(unittest.TestCase):

    def setUp(self):
        self.context_name = "context-name-fake"
        self.run_shell_patch = patch('azext_capi.helpers.kubectl.run_shell_command')
        self.run_shell_mock = self.run_shell_patch.start()
        self.run_shell_mock.return_value = None
        self.addCleanup(self.run_shell_patch.stop)

    # Test found cluster in context
    def test_existing_context(self):
        cluster_name = "cluster-name-fake"
        context_info = f"* {self.context_name} {cluster_name}"
        self.run_shell_mock.return_value = context_info
        result = find_attribute_in_context(self.context_name, "cluster")
        self.assertEquals(result, cluster_name)

    # Test does not found context
    def test_no_existing_context(self):
        self.run_shell_mock.return_value = None
        self.run_shell_mock.side_effect = subprocess.CalledProcessError(3, ['fakecommand'])
        result = find_attribute_in_context(self.context_name, "cluster")
        self.assertIsNone(result)


class CreateResourceGroup(unittest.TestCase):

    def setUp(self):
        self.cmd = Mock()
        self.group = "fake-resource-group"
        self.location = "fake-location"
        self.try_command_patch = patch('azext_capi.custom.try_command_with_spinner')
        self.try_command_mock = self.try_command_patch.start()
        self.try_command_mock.return_value = None
        self.addCleanup(self.try_command_patch.stop)

    # Test created new resource group
    def test_create_valid_resource_group(self):
        result = create_resource_group(self.cmd, self.group, self.location, True)
        self.assertTrue(result)

    # Test error creating resource group
    def test_raise_error_invalid_resource_group(self):
        self.try_command_mock.side_effect = subprocess.CalledProcessError(3, ['fakecommand'])
        with self.assertRaises(subprocess.CalledProcessError):
            create_resource_group(self.cmd, self.group, self.location, True)


class GetUserPromptMethodTest(unittest.TestCase):

    def setUp(self):
        self.fake_input = "fake-input"
        self.fake_prompt = Mock()
        self.fake_default_value = Mock()
        self.prompt_method_patch = patch('azext_capi.helpers.prompt.prompt_method')
        self.prompt_method_mock = self.prompt_method_patch.start()
        self.prompt_method_mock.return_value = None
        self.addCleanup(self.prompt_method_patch.stop)

    # Test user input return without any validation
    def test_user_input_without_validation(self):
        prompt_mock = self.prompt_method_mock
        prompt_mock.return_value = self.fake_input
        result = get_user_prompt_or_default(self.fake_prompt, self.fake_default_value)
        self.assertEquals(result, self.fake_input)

    # Test skip-prompt to return default value
    def test_skip_prompt_flag(self):
        prompt_mock = self.prompt_method_mock
        prompt_mock.return_value = None
        result = get_user_prompt_or_default(self.fake_prompt, self.fake_default_value, skip_prompt=True)
        self.assertEquals(result, self.fake_default_value)
        self.assertIsNotNone(result)

    # Test input against validation
    def test_write_user_input_with_validation(self):
        prompt_mock = self.prompt_method_mock
        valid_input = "abcd"
        regex_validator = "^[a-z]+$"
        prompt_mock.side_effect = ["Invalid-input_$(2", valid_input]
        result = get_user_prompt_or_default(self.fake_prompt, self.fake_default_value, regex_validator)
        self.assertEquals(result, valid_input)
        self.assertEquals(prompt_mock.call_count, 2)
        self.assertNotEquals(result, self.fake_default_value)

    # Test invalid user input against validation
    def test_invalid_input_with_validation(self):
        prompt_mock = self.prompt_method_mock
        regex_validator = "^[a-z]+$"
        prompt_mock.side_effect = ["Invalid-input_$(2"]
        with self.assertRaises(StopIteration):
            get_user_prompt_or_default(self.fake_prompt, self.fake_default_value, regex_validator)

    # Test user enter empty input for default value
    def test_user_skips_input_for_default_value(self):
        prompt_mock = self.prompt_method_mock
        empty_input = ""
        prompt_mock.return_value = empty_input
        result = get_user_prompt_or_default(self.fake_prompt, self.fake_default_value)
        self.assertEquals(result, self.fake_default_value)
        self.assertNotEquals(result, empty_input)


class TryCommandWithSpinner(unittest.TestCase):

    def setUp(self):
        self.cmd = Mock()
        self.msg = "Test function"
        self.error_msg = "✗ Failed to test function"
        self.command = ["fake-command"]
        self.spinner_patch = patch('azext_capi.helpers.run_command.Spinner')
        self.spinner_mock = self.spinner_patch.start()
        self.addCleanup(self.spinner_patch.stop)

    # Test valid command run
    def test_command_run(self):
        with patch('subprocess.check_output') as mock:
            try_command_with_spinner(self.cmd, self.command, self.msg)
            mock.assert_called_once()

    # Test invalid command run
    def test_invalid_command_run(self):
        with self.assertRaises(UnclassifiedUserFault) as cm:
            try_command_with_spinner(self.cmd, self.command, self.msg)
        self.assertEquals(cm.exception.error_msg, self.error_msg)

    # Test messsage variants function
    def test_message_variants(self):
        Case = namedtuple('Case', ['template', 'begin', 'end', 'error'])
        cases = [
            Case("Delete the cluster", "Deleting the cluster", "✓ Deleted the cluster", "✗ Failed to delete the cluster"),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertEquals(message_variants(case.template), (case.begin, case.end, case.error))


class CheckKubectlNamespaceTest(unittest.TestCase):

    def setUp(self):
        self.namespace = "fake"
        self.command = ["fake-command"]

        self.run_shell_command_patch = patch('azext_capi.helpers.kubectl.run_shell_command')
        self.run_shell_command_mock = self.run_shell_command_patch.start()
        self.addCleanup(self.run_shell_command_patch.stop)

        self.match_output_patch = patch('azext_capi.helpers.kubectl.match_output')
        self.match_output_mock = self.match_output_patch.start()
        self.addCleanup(self.match_output_patch.stop)

    def test_no_existing_namespace(self):
        error_msg = f"namespace: {self.namespace} could not be found!"
        error_side_effect = subprocess.CalledProcessError(2, self.command, output=error_msg)
        self.run_shell_command_mock.side_effect = error_side_effect
        with self.assertRaises(ResourceNotFoundError) as cm:
            check_kubectl_namespace(self.namespace)
        self.assertEquals(cm.exception.error_msg, error_msg)

    def test_no_active_namespace(self):
        self.run_shell_command_mock.return_value = f"{self.namespace} FakeStatus FakeAge"
        self.match_output_mock.return_value = None
        with self.assertRaises(ResourceNotFoundError) as cm:
            check_kubectl_namespace(self.namespace)
        self.assertEquals(cm.exception.error_msg, f"namespace: {self.namespace} status is not Active")

    def test_existing_namespace(self):
        self.run_shell_command_mock.return_value = f"{self.namespace} Active FakeAge"
        self.match_output_mock.return_value = True
        output = check_kubectl_namespace(self.namespace)
        self.assertIsNone(output)


class ManagementClusterComponentsMissingMatchExpressionTest(unittest.TestCase):

    ValidCases = [
        "namespace: fake could not be found",
        "No resources found in fake-ns namespace",
        "No Fake installation found"
    ]

    InvalidCases = [
        "",
        "fake",
        "Invalid",
        "No installation found"
    ]

    def test_valid_mgmt_matches(self):
        for out in self.ValidCases:
            self.assertTrue(management_cluster_components_missing_matching_expressions(out))

    def test_invalid_mgmt_matches(self):
        for out in self.InvalidCases:
            self.assertIsNone(management_cluster_components_missing_matching_expressions(out))


class AddKubeconfigFlagMethodTest(unittest.TestCase):

    def test_no_empty_kubeconfig(self):
        fake_kubeconfig = "fake-kubeconfig"
        output = add_kubeconfig_to_command(fake_kubeconfig)
        self.assertEquals(len(output), 2)
        self.assertEquals(output[1], fake_kubeconfig)

    def test_no_kubeconfig_argument(self):
        output = add_kubeconfig_to_command()
        self.assertEquals(len(output), 0)


class HasKindPrefix(unittest.TestCase):

    def test_valid_prefix(self):
        fake_input = "kind-fake"
        self.assertTrue(generic.has_kind_prefix(fake_input))

    def test_no_prefix(self):
        fake_input = "fake"
        self.assertFalse(generic.has_kind_prefix(fake_input))


class GetUrlDomainName(unittest.TestCase):

    def test_correct_url(self):
        fake_url = "https://www.notrealdomain.fake"
        result = network.get_url_domain_name(fake_url)
        self.assertIn(result, fake_url)

    def test_invalid_url(self):
        fake_url = "invalid-url"
        result = network.get_url_domain_name(fake_url)
        self.assertIsNone(result)


class GetDefaultBootstrapCommandsTest(unittest.TestCase):

    def test_get_default_kubeadm_for_windows(self):
        result = get_default_bootstrap_commands(windows=True)
        self.assertIsNotNone(result)
        self.assertEquals(len(result["pre"]), 0)
        self.assertNotEquals(len(result["post"]), 0)

    def test_get_default_kubeadm_no_windows(self):
        result = get_default_bootstrap_commands()
        self.assertIsNotNone(result)
        self.assertEqual(result["pre"], [])
        self.assertEqual(result["post"], [])


class ParseKubeadmCommandsFromFileTest(unittest.TestCase):

    def setUp(self):
        self.os_path_isfile_patch = patch('os.path.isfile')
        self.os_path_isfile_mock = self.os_path_isfile_patch.start()
        self.addCleanup(self.os_path_isfile_patch.stop)
        self.fake_valid_output = {
            "pre": ["fake-pre-cmd"],
            "post": ["fake-post-cmd"]
        }

        self.yaml_load_patch = patch('yaml.load')
        self.yaml_load_mock = self.yaml_load_patch.start()
        self.addCleanup(self.yaml_load_patch.stop)

        self.open_patch = patch('azext_capi.custom.open')
        self.open_mock = self.open_patch.start()
        self.addCleanup(self.open_patch.stop)

    def test_get_bootstrap_commands_no_valid_file_path(self):
        self.os_path_isfile_mock.return_value = False
        with self.assertRaises(InvalidArgumentValueError):
            parse_bootstrap_commands_from_file("fake-path")

    def test_get_bootstrap_commands_valid_file_both_commands(self):
        self.os_path_isfile_mock.return_value = True
        fake_file_value = {
            "preBootstrapCommands": ["fake-pre-cmd"],
            "postBootstrapCommands": ["fake-post-cmd"]
        }
        self.yaml_load_mock.return_value = fake_file_value
        result = parse_bootstrap_commands_from_file("fake-path")
        self.assertEqual(result, self.fake_valid_output)

    def test_get_bootstrap_commands_valid_file_pre_commands(self):
        self.os_path_isfile_mock.return_value = True
        fake_output = {
            "preBootstrapCommands": ["fake-pre-cmd"]
        }
        expected_output = {
            "pre": ["fake-pre-cmd"],
            "post": []
        }
        self.yaml_load_mock.return_value = fake_output
        result = parse_bootstrap_commands_from_file("fake-path")
        self.assertEqual(result, expected_output)

    def test_get_bootstrap_commands_valid_file_post_commands(self):
        self.os_path_isfile_mock.return_value = True
        fake_output = {
            "preBootstrapCommands": ["fake-post-cmd"]
        }
        expected_output = {
            "pre": ["fake-post-cmd"],
            "post": []
        }
        self.yaml_load_mock.return_value = fake_output
        result = parse_bootstrap_commands_from_file("fake-path")
        self.assertEqual(result, expected_output)


class IsClusterctlCompatible(unittest.TestCase):

    Compatible = [
        "https://github.com/kubernetes-sigs/cluster-api-provider-azure/blob/main/templates/addons/windows/calico/kube-proxy-windows.yaml",
        "https://github.com/kubernetes-sigs/cluster-api-provider-azure/blob/main/templates/cluster-template.yaml"
    ]

    NotCompatible = [
        "https://github.com/kubernetes-sigs/cluster-api-provider-azure/releases/download/v1.3.1/cluster-template-aad.yaml",
        "https://storage.googleapis.com/kubernetes-jenkins/pr-logs/pull/kubernetes-sigs_cluster-api-provider-azure/2345/pull-cluster-api-provider-azure-e2e/1532067150565478400/artifacts/clusters/bootstrap/capz-e2e-8nykgw-public-custom-vnet-cluster-template.yaml",
        "https://test.com/someurl.yaml",
        "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api-provider-azure/main/templates/addons/windows/calico/kube-proxy-windows.yaml",
        "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api-provider-azure/main/templates/cluster-template-aad.yaml"
    ]

    def setUp(self):
        self.os_path_isfile_patch = patch('os.path.isfile')
        self.os_path_isfile_mock = self.os_path_isfile_patch.start()
        self.os_path_isfile_mock.return_value = False
        self.addCleanup(self.os_path_isfile_patch.stop)

    def test_valid_matches(self):
        for out in self.Compatible:
            self.assertTrue(generic.is_clusterctl_compatible(out))

    def test_invalid_matches(self):
        for out in self.NotCompatible:
            self.assertFalse(generic.is_clusterctl_compatible(out))

    def test_localfile_is_compatible(self):
        self.os_path_isfile_mock.return_value = True
        self.assertTrue(generic.is_clusterctl_compatible("testfile.yaml"))
        self.assertTrue(generic.is_clusterctl_compatible("./testfile.yaml"))


class TestGenerateClusterName(unittest.TestCase):

    def test_generate_cluster_name(self):
        cases = {
            4990: "rococo-aqualung",
            4991: "guided-vocalist",
            4992: "hungry-inventor",
            4993: "timely-renegade",
            4994: "clever-earthman",
            4995: "vulcan-instinct",
            4996: "iconic-tabletop",
            4997: "zircon-goldfish",
            4998: "ultima-electron",
            4999: "steely-footwear",
        }
        for seed, name in cases.items():
            self.assertEqual(generate_cluster_name(seed), name)


class TestPrepKubeConfig(unittest.TestCase):

    def test_prepkubeconfig(self):
        cases = {
            "good": """\
apiVersion: v1
kind: Config
preferences: {}
clusters: []
contexts: []
users: []
""",
            "bad": """\
apiVersion: v1
kind: Config
preferences: {}
"""
        }
        for label in cases:
            kubeconfig = cases[label]
            original_config = os.environ.pop("KUBECONFIG", None)
            with tempfile.NamedTemporaryFile("w") as f:
                os.environ["KUBECONFIG"] = f.name
                f.write(kubeconfig) and f.flush()
                prep_kube_config()
                config = yaml.safe_load(open(f.name))
            self.assertEqual(config["apiVersion"], "v1")
            self.assertEqual(config["kind"], "Config")
            self.assertIsInstance(config["preferences"], dict)
            self.assertIn("clusters", config) and self.assertIsInstance(config["clusters"], list)
            self.assertIn("contexts", config) and self.assertIsInstance(config["contexts"], list)
            self.assertIn("users", config) and self.assertIsInstance(config["users"], list)
            if original_config:
                os.environ["KUBECONFIG"] = original_config
            else:
                del os.environ["KUBECONFIG"]


class TestGetArch(unittest.TestCase):

    def test_get_arch(self):
        cases = {
            "amd64": "amd64",
            "AMD64": "amd64",
            "x86_64": "amd64",
            "arm64": "arm64",
            "aarch64": "arm64",
            "armv7l": "arm",
            "ppc64le": "ppc64le",
            "s390x": "s390x",
            "unknown": "unknown",
        }
        for arch, expected in cases.items():
            self.assertEqual(get_arch(arch), expected)
