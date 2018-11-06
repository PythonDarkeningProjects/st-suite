from imp import reload
import os
import getpass
import subprocess
import pexpect

import psutil

from Config import config
from Libraries import common
from Utils import logger

# reloading config.ini
reload(config)

# Global variables
THIS_PATH = os.path.dirname(os.path.abspath(__file__))
CURRENT_USER = getpass.getuser()
PASSWORD = config.get('credentials', 'some_variable')
PROMPT = '$'

# setup the logger
LOG_FILENAME = 'iso_setup.log'
LOG_PATH = config.get('general', 'LOG_PATH')
LOG = logger.setup_logging(
    'iso_setup', log_file='{path}/{filename}'.format(
        path=LOG_PATH, filename=LOG_FILENAME), console_log=False)


class Installer(object):
    """Some description"""

    def __init__(self):
        self.child = pexpect.spawn(config.get('installer', 'VIRSH_CMD'))
        self.child.logfile = open('{}/output.txt'.format(
            LOG_PATH), 'wb')

    @staticmethod
    def open_xterm_console():
        """Open a xterm console to visualize logs from serial connection"""

        suite_path = os.path.dirname(THIS_PATH)
        terminal = 'xterm'
        terminal_title = '"boot console"'
        geometry = '-0+0'  # upper right hand corner
        os.environ['DISPLAY'] = ':0'
        command = 'python {suite}/Utils/watcher.py {log_path}'.format(
            suite=suite_path, log_path=LOG_PATH)

        try:
            pid_list = subprocess.check_output(['pidof', terminal]).split()

            # killing all xterm active sessions
            for pid in pid_list:
                _pid = psutil.Process(int(pid))
                # terminate the process
                _pid.terminate()

                if _pid.is_running():
                    # forces the process to terminate
                    _pid.suspend()
                    _pid.resume()
        except subprocess.CalledProcessError:
            LOG.info('There is not process for : {}'.format(terminal))

        os.system('{term} -geometry {geo} -T {title} -e {cmd} &'.format(
            term=terminal, geo=geometry, title=terminal_title, cmd=command))

    def boot_installer(self):
        boot_timeout = int(config.get('installer', 'BOOT_TIMEOUT'))
        self.child.expect('Escape character')
        # send a escape character
        self.child.sendline('\x1b')
        self.child.expect('boot:')
        cmd_boot_line = common.get_cmd_boot_line()
        self.child.sendline(cmd_boot_line)
        LOG.info('kernel command line sent: {}'.format(cmd_boot_line))
        # send a enter character
        self.child.sendline('\r')
        # setting a boot timeout
        self.child.timeout = boot_timeout
        self.child.expect('Loading vmlinuz')
        LOG.info('Loading vmlinuz')
        self.child.expect('Loading initrd.img')
        LOG.info('Loading initrd.img')
        self.child.expect('Starting installer, one moment...')
        LOG.info('Starting installer ...')
        self.child.expect('Performing post-installation setup tasks')
        LOG.info('Performing post-installation setup tasks')

    def first_login(self):
        """Change the password at first login"""

        user_name = config.get('credentials', 'some_variable')
        self.child.expect('localhost login:')
        LOG.info('the system boot up correctly')
        LOG.info('logging into the system')
        self.child.sendline(user_name)
        self.child.expect('Password:')
        self.child.sendline(user_name)
        LOG.info('setting a new password')
        self.child.expect('UNIX password:')
        self.child.sendline(user_name)
        self.child.expect('New password:')
        self.child.sendline(PASSWORD)
        self.child.expect('Retype new password:')
        self.child.sendline(PASSWORD)
        self.child.expect('$')
        LOG.info('the password was changed successfully')

    def configure_temp_network(self):
        """Setup a temporal IP"""

        tmp_ip = config.get('installer', 'some_variable')
        tmp_interface = config.get(
            'installer', 'some_variable')
        tmp_gateway = config.get(
            'iso_installer', 'CONTROLLER_TMP_GATEWAY')
        LOG.info('Configuring temporal network')
        self.child.expect(PROMPT)
        self.child.sendline('sudo ip addr add {0}/24 dev {1}'.format(
            tmp_ip, tmp_interface))
        self.child.expect('Password:')
        self.child.sendline(PASSWORD)

        self.child.expect(PROMPT)
        self.child.sendline('sudo ip link set {} up'.format(
            tmp_interface))

        self.child.expect(PROMPT)
        self.child.sendline('sudo ip route add default via {}'.format(
            tmp_gateway))

        LOG.info('Network configured, testing ping')
        self.child.sendline('ping -c 1 127.0.0.1')
        self.child.expect('1 packets transmitted')
        LOG.info('Ping successful')

    def config(self, config_file):

        config_timeout = int(config.get(
            'installer', 'CONFIG_CONTROLLER_TIMEOUT'))
        self.child.expect(PROMPT)
        LOG.info('Applying configuration (this will take several minutes)')
        self.child.sendline('sudo some_line --config-file {}'.format(
            config_file))
        self.child.timeout = config_timeout
        self.child.expect('Configuration was applied')
        LOG.info(self.child.before)

    def finish_logging(self):
        """Stop logging and close log file"""
        self.child.logfile.close()
        LOG.info('Closing the log')


def install():
    install_obj = Installer()
    install_obj.open_xterm_console()
    install_obj.boot_installer()
    install_obj.first_login()
    install_obj.configure_temp_network()
    return install_obj


def config(connection, config_file):
    connection.config(config_file)
    connection.finish_logging()
