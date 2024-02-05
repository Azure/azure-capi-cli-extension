# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
This module contains helper functions for the az capi extension.
"""
from urllib.parse import urlparse
import ssl

from six.moves.urllib.request import urlopen


def ssl_context():
    """Returns an SSL context appropriate for the python version and environment."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def urlretrieve(url, filename):
    """Retrieves the contents of a URL to a file."""
    req = urlopen(url, context=ssl_context())  # pylint: disable=consider-using-with
    with open(filename, "wb") as out:
        out.write(req.read())


def get_url_domain_name(url):
    domain = urlparse(url).netloc
    return domain if domain else None
