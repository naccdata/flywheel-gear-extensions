"""Provides commandline argument parsing for script used in a gear that is
expecting a file and a dry run flag.

Includes gear flag so that script knows to look for arguments in gear
context.
"""
import argparse


def build_parser_with_input() -> argparse.ArgumentParser:
    """Builds and returns the argument parser."""
    parser = build_base_parser()
    parser.add_argument('filename', help='path of input file')
    return parser


def build_parser_with_output() -> argparse.ArgumentParser:
    """Builds and returns an argument parser with an output file."""
    parser = build_base_parser()
    parser.add_argument('filename', help='path for output file')
    return parser


def build_base_parser() -> argparse.ArgumentParser:
    """Builds an argument parser with arguments to indicate running as a gear,
    whether to do a dry run, and the name of the admin group."""
    parser = argparse.ArgumentParser(
        description="Create FW structures for Project")
    parser.add_argument(
        '--gear',
        help='read arguments from gear input, use --no-gear for cli arguments',
        default=True,
        action=argparse.BooleanOptionalAction)
    parser.add_argument('--dry_run',
                        help='do a dry run to check input file',
                        default=False,
                        action='store_true')
    parser.add_argument('--new_only',
                        help='Whether to only add new centers',
                        default=False,
                        action='store_true')
    parser.add_argument('--admin_group',
                        help='Group ID for the admin group',
                        default='nacc')

    return parser
