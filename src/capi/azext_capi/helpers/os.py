# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os


def set_environment_variables(dic=None):
    """
    Sets the key and value items of a dictionary into environment variables.
    """
    if not dic:
        return
    for key, value in dic.items():
        if value:
            os.environ[key] = f"{value}"


def write_to_file(filename, file_input):
    """
    Writes file_input into file
    """
    with open(filename, "w", encoding="utf-8") as manifest_file:
        manifest_file.write(file_input)
