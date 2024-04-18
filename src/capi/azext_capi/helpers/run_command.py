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


def run_shell_command(command, combine_std=True, mask_fields=None):
    # if --verbose, don't capture stderr
    stderr = None
    if combine_std:
        stderr = None if is_verbose() else subprocess.STDOUT
    output = subprocess.check_output(command, universal_newlines=True, stderr=stderr)
    log_output = mask(output, mask_fields)
    logger.info("%s returned:\n%s", " ".join(command), log_output)
    return output


def mask(output, mask_fields):
    """Mask all instances of mask_fields with "****" in JSON or YAML output."""
    if mask_fields and output:
        for field in mask_fields:
            output = mask_field(output, field)
    return output


def mask_field(output, key):
    """Mask all instances of key with "****" in JSON or YAML output."""
    lines = []
    for line in output.splitlines():
        if line.strip().replace('"', '').startswith(key + ": "):
            maybe_comma = "," if line.endswith(",") else ""
            lines.append(line.split(": ")[0] + ': "****"' + maybe_comma)
        else:
            lines.append(line)
    return "\n".join(lines)


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
