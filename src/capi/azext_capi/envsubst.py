# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Substitutes environment variables in shell-formatted strings.

>>> envsubst('${var}', {'var': 'value'})
'value'
"""

import os
import re


def envsubst(s, env):
    """Substitutes environment variables in shell-formatted strings."""
    # ${var,,} -> lowercase all characters of variable
    s = re.sub(r'\$\{([^{}]+),,\}', lambda m: env[m.group(1)].lower(), s)
    # ${var,} -> lowercase first character of variable
    s = re.sub(r'\$\{([^{}]+),\}', lambda m: env[m.group(1)][:1].lower() + env[m.group(1)][1:], s)
    # ${var^^} -> uppercase all characters of variable
    s = re.sub(r'\$\{([^{}]+)\^\^\}', lambda m: env[m.group(1)].upper(), s)
    # ${var^} -> uppercase first character of variable
    s = re.sub(r'\$\{([^{}]+)\^\}', lambda m: env[m.group(1)][:1].upper() + env[m.group(1)][1:], s)
    # ${#var} -> string length of variable
    s = re.sub(r'\$\{#([^{}]+)\}', lambda m: str(len(env[m.group(1)])), s)
    # ${var:pos} -> value of variable from a string position to end
    s = re.sub(r'\$\{([^{}:]+):([^{}:=-]+)\}', lambda m: env[m.group(1)][int(m.group(2)):], s)
    # ${var:pos:len} -> value of variable from a string position with max length
    s = re.sub(r'\$\{([^{}:]+):([^{}:=-]+):([^{}:=-]+)\}',
               lambda m: env[m.group(1)][int(m.group(2)):int(m.group(2)) + int(m.group(3))], s)
    # ${var} -> simple value of variable
    s = re.sub(r'\$\{([^{}:=-]+)\}', lambda m: env[m.group(1)], s)
    # ${var:=default} -> evaluate default expression if variable is not set or empty
    s = re.sub(r'\$\{([^}]+):[=-]([^}]+)\}', lambda m: env[m.group(1)] if env.get(m.group(1)) else m.group(2), s)
    # ${var=default} -> evaluate default expression if variable is not set
    s = re.sub(r'\$\{([^}]+)[=-]([^}]+)\}', lambda m: env[m.group(1)] if m.group(1) in env else m.group(2), s)
    return s


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        import doctest
        doctest.testmod()
        print('Usage: envsubst.py <string_or_filename>\n')
    else:
        arg = sys.argv[1]
        if os.path.isfile(arg):
            with open(arg, 'r', encoding='utf-8') as f:
                print(envsubst(f.read(), os.environ))
        else:
            print(envsubst(arg, os.environ))
