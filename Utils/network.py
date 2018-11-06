"""Provides different network functions"""

import logging
from bash import bash
import subprocess

from elevate import elevate
from ifparser import Ifcfg
from pynetlinux import ifconfig
from pynetlinux import brctl

LOG = logging.getLogger(__name__)


def delete_network_interfaces():
    """Delete network interfaces

    This function performs a clean up for the following network interfaces
    virbr[1-4]
    """

    # elevate module re-launches the current process with root/admin privileges
    # using one of the following mechanisms : sudo (Linux, macOS)

    # becoming in root
    elevate(graphical=False)

    ifdata = Ifcfg(subprocess.check_output(['ifconfig', '-a']))

    for interface in range(1, 5):
        current_interface = 'virbr{}'.format(interface)

        if current_interface in ifdata.interfaces:
            # the network interface exists
            net_object = ifdata.get_interface(current_interface)
            net_up = net_object.get_values().get('UP')
            net_running = net_object.get_values().get('RUNNING')

            if net_up or net_running:
                # the network interface is up or running
                try:
                    # down and delete the network interface
                    ifconfig.Interface(current_interface).down()
                    brctl.Bridge(current_interface).delete()
                except IOError:
                    LOG.warn('[Errno 19] No such device: {}'.format(
                        current_interface))

        # adding the network interface
        try:
            brctl.addbr(current_interface)
        except IOError:
            LOG.warn('[Errno 17] File exists {}'.format(current_interface))


def configure_network_interfaces():
    """Configure network interfaces

    This function configure the following network interfaces virbr[1-4]
    """
    networks = ['virbr1 10.10.10.1/24', 'virbr2 192.168.204.1/24',
                'virbr3', 'virbr4']

    for net in networks:
        eval_cmd = bash('sudo ifconfig {} up'.format(net))
        if 'ERROR' in eval_cmd.stderr:
            LOG.error(eval_cmd.stderr)
            raise EnvironmentError(eval_cmd.stderr)

    # setting the ip tables
    iptables = ('sudo iptables -t nat -A POSTROUTING -s 10.10.10.0/24 -j '
                'MASQUERADE')

    eval_cmd = bash(iptables)
    if 'ERROR' in eval_cmd.stderr:
        LOG.error(eval_cmd.stderr)
        raise EnvironmentError(eval_cmd.stderr)
