# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains helper functions for the az capi extension.
"""

import re

from knack.prompting import prompt as prompt_method

from .logger import logger


def get_cluster_name_by_user_prompt(default_name):
    """Prompts user for management cluster name"""
    prompt = "Please name the management cluster"
    regex_validator = "^[a-z0-9.-]+$"
    invalid_msg = "Invalid name for cluster: only lowercase characters, numbers, dashes and periods allowed"
    return get_user_prompt_or_default(prompt, default_name, regex_validator, invalid_msg)


def get_user_prompt_or_default(prompt_text, default_value, match_expression=None,
                               invalid_prompt=None, skip_prompt=False):
    """Prompts user for input or uses default value"""
    if skip_prompt:
        return default_value

    prompt = f"{prompt_text} [Default {default_value}]: "
    while True:
        user_input = prompt_method(prompt)
        user_input = user_input.strip()
        if user_input == "":
            return default_value
        if match_expression and re.match(match_expression, user_input):
            return user_input
        if not match_expression:
            return user_input
        if invalid_prompt:
            logger.error(invalid_prompt)
