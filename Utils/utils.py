"""Provides a library of useful utilities.

This module provides a list of general purpose utilities. Those functions that
are part of a larger domain, for example functions related to networking,
should be provided by a different module.

This module should only include functions that are not related with a
specific application, in other words these methods should be application
agnostic.
"""

from __future__ import print_function

import os
import timeit
import pwd

import bash_utils as bash


def find_owner(element):
    """Find the owner of a file or folder

    :param element: which can be a file or folder to check
    :return
        - the user that own the file or folder
    """

    return pwd.getpwuid(os.stat(element).st_uid).pw_name


def isdir(path, sudo=True):
    """Validates if a directory exist in a host.

    :param path: the path of the directory to be validated
    :param sudo: this needs to be set to True for directories that require
    root permission
    :return: True if the directory exists, False otherwise
    """
    status, _ = bash.run_command(
        '{prefix}test -d {path}'.format(
            path=path, prefix='sudo ' if sudo else ''))
    exist = True if not status else False
    return exist


def isfile(path, sudo=True):
    """Validates if a file exist in a host.

    :param path: the absolute path of the file to be validated
    :param sudo: this needs to be set to True for files that require
    root permission
    :return: True if the file exists, False otherwise
    """
    status, _ = bash.run_command(
        '{prefix}test -f {path}'.format(
            path=path, prefix='sudo ' if sudo else ''))
    exist = True if not status else False
    return exist


def timer(action, print_elapsed_time=True):
    """Function that works as a timer, with a start/stop button.

    :param action: the action to perform, the valid options are:
        - start: start a counter for an operation
        - stop: stop the current time
    :param print_elapsed_time: if set to False the message is not printed to
    console, only returned
    :return: the elapsed_time string variable
    """
    elapsed_time = 0
    if action.lower() == 'start':
        start = timeit.default_timer()
        os.environ['START_TIME'] = str(start)
    elif action.lower() == 'stop':
        if 'START_TIME' not in os.environ:
            bash.message('err', 'you need to start the timer first')
            return None
        stop = timeit.default_timer()
        total_time = stop - float(os.environ['START_TIME'])
        del os.environ['START_TIME']

        # output running time in a nice format.
        minutes, seconds = divmod(total_time, 60)
        hours, minutes = divmod(minutes, 60)
        elapsed_time = 'elapsed time ({h}h:{m}m:{s}s)'.format(
            h=0 if round(hours, 2) == 0.0 else round(hours, 2),
            m=0 if round(minutes, 2) == 0.0 else round(minutes, 2),
            s=round(seconds, 2))
        if print_elapsed_time:
            bash.message('info', elapsed_time)
    else:
        bash.message('err', '{0}: not allowed'.format(action))

    return elapsed_time
