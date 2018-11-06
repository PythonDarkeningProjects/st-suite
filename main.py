#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Runner for StarlingX test suite"""

from __future__ import print_function

import argparse
import getpass
import os

import robot
import Utils.common as common
from Libraries.common import update_config_ini

# Global variables
CURRENT_USER = getpass.getuser()
SUITE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SUITE = os.path.join(SUITE_DIR, 'Tests')
LOG_NAME = 'debug.log'

# Set PYHTHONPATH variable
os.environ["PYTHONPATH"] = SUITE_DIR


def get_args():
    """Define and handle arguments with options to run the script

    Return:
        parser.parse_args(): list arguments as objects assigned
            as attributes of a namespace
    """

    description = "Script used to run sxt-test-suite"
    parser = argparse.ArgumentParser(description=description)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--list-suites', dest='list_suite_name',
        nargs='?', const=os.path.basename(MAIN_SUITE),
        help=(
            'List the suite and sub-suites including test cases of the '
            'specified suite, if no value is given the entire suites tree '
            'is displayed.'))
    group.add_argument('--run-all', dest='run_all',
                       action='store_true', help='Run all available suites')
    group.add_argument('--run-suite', dest='run_suite_name',
                       help='Run the specified suite')
    group_extras = parser.add_argument_group(
        'Execution Extras', 'Extra options to be used on the suite execution.')
    group_extras.add_argument(
        '--include', dest='tags',
        help=(
            'Executes only the test cases with specified tags.'
            'Tags and patterns can also be combined together with `AND`, `OR`,'
            'and `NOT` operators.'
            'Examples: --include foo --include bar* --include fooANDbar*'))
    return parser.parse_args()


def list_suites_option(suite_to_list):
    """Display the suite tree including test cases

        Args:
            suite_to_list: name of the suite to display on stdout
    """

    # Get suite details
    suite = common.Suite(suite_to_list, MAIN_SUITE)
    print(
        '''
Suite is located at: {}
=== INFORMATION ====
[S] = Suite
(T) = Test Case
====================

=== SUITE TREE ====
    '''.format(suite.path))

    common.list_suites(suite.data, '')


def run_suite_option(suite_name):
    """Run Specified Test Suite and creates the results structure

    Args:
        suite_name: name of the suite that will be executed
    """

    # Get suite details
    suite = common.Suite(suite_name, MAIN_SUITE)
    # Create results directory if does not exist
    results_dir = common.check_results_dir(SUITE_DIR)
    # Create output directory to store execution results
    output_dir = common.create_output_dir(results_dir, suite.name)
    # Create a link pointing to the latest run
    common.link_latest_run(SUITE_DIR, output_dir)
    # Updating config.ini LOG_PATH variable with output_dir
    config_path = os.path.join(SUITE_DIR, 'Config', 'config.ini')
    update_config_ini(config_ini=config_path, LOG_PATH=output_dir)
    # Select tags to be used, empty if not set to execute all
    if ARGS.tags:
        include_tags = ARGS.tags
    else:
        include_tags = ''
    # Run sxt-test-suite using robot framework
    robot.run(suite.path, outputdir=output_dir, debugfile=LOG_NAME,
              variable='LOGS_DIR:{}'.format(output_dir), include=include_tags)


if __name__ == '__main__':
    if CURRENT_USER == 'root':
        raise RuntimeError('DO NOT RUN AS ROOT')
    # Validate if script is called with at least one argument
    # Get args variables
    ARGS = get_args()
    # Check options selected
    if ARGS.list_suite_name:
        list_suites_option(ARGS.list_suite_name)
    elif ARGS.run_all:
        run_suite_option(os.path.basename(MAIN_SUITE))
    elif ARGS.run_suite_name:
        run_suite_option(ARGS.run_suite_name)
