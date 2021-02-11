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

    from azure.cli.core.commands.parameters import tags_type

    capi_name_type = CLIArgumentType(
        options_list='--capi-name-name', help='Name of the Capi.', id_part='name')

    with self.argument_context('capi') as ctx:
        ctx.argument('tags', tags_type)
        ctx.argument('capi_name', capi_name_type, options_list=['--name', '-n'])

    with self.argument_context('capi list') as ctx:
        ctx.argument('capi_name', capi_name_type, id_part=None)

    # with self.argument_context('capi init') as ctx:
    #     ctx.argument('install_location', type=file_type, completer=FilesCompleter(),
    #                  default=_get_default_install_location('kubectl'))


def _get_default_install_location(exe_name):
    system = platform.system()
    if system == 'Windows':
        home_dir = os.environ.get('USERPROFILE')
        if not home_dir:
            return None
        install_location = os.path.join(
            home_dir, r'.azure-{0}\{0}.exe'.format(exe_name))
    elif system in ('Linux', 'Darwin'):
        install_location = '/usr/local/bin/{}'.format(exe_name)
    else:
        install_location = None
    return install_location
