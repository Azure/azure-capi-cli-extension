# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from collections import namedtuple
import unittest

from azext_capi.envsubst import envsubst


class TestEnvsubst(unittest.TestCase):

    Case = namedtuple('Case', ['input', 'output', 'env'])

    cases = [
        # Simple value of variable
        Case('${FOO}', 'bar', {'FOO': 'bar'}),
        # String length of variable
        Case('${#FOO}', '3', {'FOO': 'bar'}),
        # Uppercase first character of variable
        Case('${FOO^}', 'BaR', {'FOO': 'baR'}),
        # Uppercase all characters of variable
        Case('${FOO^^}', 'BAR', {'FOO': 'bar'}),
        # Lowercase first character of variable
        Case('${FOO,}', 'bAr', {'FOO': 'BAr'}),
        # Lowercase all characters of variable
        Case('${FOO,,}', 'bar', {'FOO': 'BAR'}),
        # Value of variable from a string position to end
        Case('${FOO:1}', 'ar', {'FOO': 'bar'}),
        # Value of variable from a string position with max length
        Case('${FOO:1:1}', 'a', {'FOO': 'bar'}),
        # Evaluate default expression if variable is not set
        Case('${FOO=bar}', 'bar', {}),
        Case('${FOO=bar}', '', {'FOO': ''}),
        Case('${FOO-bar}', 'bar', {}),
        Case('${FOO-bar}', '', {'FOO': ''}),
        # Evaluate default expression if variable is not set or empty
        Case('${FOO:-bar}', 'bar', {'FOO': ''}),
        Case('${FOO:-bar}', 'bar', {}),
        Case('${FOO:=bar}', 'bar', {'FOO': ''}),
        Case('${FOO:=bar}', 'bar', {}),
        # Handle nested expressions
        Case('${FOO=${BAR^}}', 'Bar', {'BAR': 'bar'}),
        Case('${FOO:=${BAR}-baz}', 'bar-baz', {'BAR': 'bar'}),
        Case('${AZURE_VNET_NAME:=${CLUSTER_NAME}-vnet}',
             'my-cluster-vnet', {'CLUSTER_NAME': 'my-cluster'}),
    ]

    def test_envsubst(self):
        for case in self.cases:
            self.assertEqual(envsubst(case.input, case.env), case.output)
