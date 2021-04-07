# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module defines the parameters (aka arguments) for `az capi` commands.
"""

import os
import os.path
import platform

from knack.arguments import CLIArgumentType


def load_arguments(self, _):
    """Loads command arguments into the parser."""

    capi_name_type = CLIArgumentType(
        options_list='--capi-name-name', help='Name of the CAPI Kubernetes cluster.')

    with self.argument_context('capi') as ctx:
        ctx.argument('capi_name', capi_name_type, options_list=['--name', '-n'])
        ctx.argument('yes', options_list=['--yes', '-y'])


def get_virtualenv():
    return os.getenv("VIRTUAL_ENV")


def _get_default_install_location(exe_name):
    install_location = None
    system = platform.system()
    if system == 'Windows':
        home_dir = os.environ.get('USERPROFILE')
        if not home_dir:
            return None
        install_location = os.path.join(
            home_dir, r'.azure-{0}\{0}.exe'.format(exe_name))
    elif system in ('Linux', 'Darwin'):
        venv = get_virtualenv()
        if venv:
            install_location = '{}/bin/{}'.format(venv, exe_name)
        else:
            install_location = '/usr/local/bin/{}'.format(exe_name)
    return install_location
