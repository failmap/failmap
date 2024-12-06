#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "websecmap.settings")

    # chicken and egg problem, import can only be done when the environment is setup correctly.
    from django.core.management import execute_from_command_line  # pylint: disable=import-outside-toplevel

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
