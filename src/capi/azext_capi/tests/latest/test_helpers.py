# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import platform
import sys
import tempfile
import unittest
from collections import namedtuple
from unittest.mock import patch, MagicMock

import azext_capi._helpers as helpers


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
                        self.assertTrue(helpers.ssl_context())


class TestURLRetrieveHelper(unittest.TestCase):

    @patch('azext_capi._helpers.urlopen')
    def test_urlretrieve(self, mock_urlopen):
        random_bytes = os.urandom(2048)
        req = mock_urlopen.return_value
        req.read.return_value = random_bytes
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.close()
            helpers.urlretrieve('https://dummy.url', fp.name)
            self.assertEqual(open(fp.name, 'rb').read(), random_bytes)
            os.unlink(fp.name)
