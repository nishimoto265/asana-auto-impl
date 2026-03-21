#!/usr/bin/env python3
"""Parse Asana task JSON from stdin and print fields.

Usage: curl ... | python3 -m lib.parse_task_json <field> [<field> ...]

Supported fields: name, notes, permalink_url
Each requested field is printed on its own line.
"""

import json
import sys


def main() -> None:
    fields = sys.argv[1:]
    if not fields:
        print("Usage: parse_task_json.py <field> [<field> ...]", file=sys.stderr)
        sys.exit(1)

    data = json.load(sys.stdin).get("data", {})
    for field in fields:
        print(data.get(field, ""))


if __name__ == "__main__":
    main()
