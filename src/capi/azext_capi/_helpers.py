import platform
import ssl
import sys

from six.moves.urllib.request import urlopen

from azure.cli.core.util import in_cloud_console


def ssl_context():
    if sys.version_info < (3, 4) or (in_cloud_console() and platform.system() == "Windows"):
        try:
            # added in python 2.7.13 and 3.6
            return ssl.SSLContext(ssl.PROTOCOL_TLS)
        except AttributeError:
            return ssl.SSLContext(ssl.PROTOCOL_TLSv1)

    return ssl.create_default_context()


def urlretrieve(url, filename):
    req = urlopen(url, context=ssl_context())
    with open(filename, "wb") as out:
        out.write(req.read())
