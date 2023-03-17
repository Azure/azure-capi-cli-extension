# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=missing-docstring

import subprocess
import time

from azure.cli.core.azclierror import UnclassifiedUserFault

from .spinner import Spinner
from .logger import logger, is_verbose


def run_shell_command(command, combine_std=True):
    # if --verbose, don't capture stderr
    stderr = None
    if combine_std:
        stderr = None if is_verbose() else subprocess.STDOUT
    output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
    logger.info("%s returned:\n%s", " ".join(command), output)
    return output


def message_variants(template_msg):
    # Find the first word and assume it's a capitalized verb.
    verb, predicate = template_msg.split(" ", 1)
    begin_msg = f"{verb[:-1]}ing {predicate}" if verb.endswith("e") else f"{verb}ing {predicate}"
    end_msg = f"✓ {verb}d {predicate}" if verb.endswith("e") else f"✓ {verb}ed {predicate}"
    error_msg = f"✗ Failed to {verb.lower()} {predicate}"
    return begin_msg, end_msg, error_msg


def try_command_with_spinner(cmd, command, spinner_msg, include_error_stdout=False):
    begin_msg, end_msg, err_msg = message_variants(spinner_msg)
    with Spinner(cmd, begin_msg, end_msg):
        try:
            run_shell_command(command)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            if include_error_stdout:
                err_msg += f"\n{err.stdout}"
            raise UnclassifiedUserFault(err_msg) from err


def retry_shell_command(command, attempts=100, delay=3):
    """Run a shell command, retrying a number of times with a specified delay if it fails."""
    output = ""
    for i in range(attempts):
        try:
            output = run_shell_command(command)
            break
        except subprocess.CalledProcessError as err:
            logger.info(err)
            if i == attempts - 1:
                raise
            time.sleep(delay)
    return output
