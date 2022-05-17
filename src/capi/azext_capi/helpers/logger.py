# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=missing-docstring

import logging
from functools import lru_cache

from knack.log import get_logger

logger = get_logger()  # pylint: disable=invalid-name


@lru_cache(maxsize=None)
def is_verbose():
    return any(handler.level <= logging.INFO for handler in logger.handlers)
