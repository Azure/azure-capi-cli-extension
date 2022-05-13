# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=missing-docstring

import os


def set_enviroment_variables(dic):
    for key, value in dic.items():
        if value:
            os.environ.setdefault(key, f"{value}")


def write_to_file(filename, file_input):
    with open(filename, "w", encoding="utf-8") as manifest_file:
        manifest_file.write(file_input)
