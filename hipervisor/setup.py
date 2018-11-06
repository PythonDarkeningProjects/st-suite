from __future__ import print_function

import argparse
from argparse import RawDescriptionHelpFormatter
from imp import reload
import multiprocessing
import os
import re
from shutil import rmtree
import sys

# this needs to be exactly here after call network.delete_network_interfaces()
# otherwise the suite local modules they will not be recognized
SUITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(SUITE_DIR)

from Config import config
from Utils import bash_utils as bash
from Utils import logger
from Utils import network
import kmodpy
import yaml

# reloading config.ini
reload(config)

# Global variables
THIS_PATH = os.path.dirname(os.path.abspath(__file__))

# setup the logger
LOG_FILENAME = 'setup.log'
LOG_PATH = config.get('general', 'LOG_PATH')
LOG = logger.setup_logging(
    'setup', log_file='{path}/{filename}'.format(
        path=LOG_PATH, filename=LOG_FILENAME), console_log=False)


def exit_dict_status(code):
    """Exit status

    The aim of this function is to provide a exit status in dictionary format
    as an string in order to grab it for for perform actions.

    :param code: which is the exit status code
        code 0: which represents an exit status god.
        code 1: which represents an exit status bad.
    """
    # defining the dictionary

    if code == 1:
        LOG.info('status: FAIL')
    elif code == 0:
        LOG.info('status: PASS')
    else:
        LOG.error('exit code not valid')

    sys.exit(code)


def check_kernel_virtualization():
    km = kmodpy.Kmod()
    module_list = [m for m in km.list()]

    virtualization = filter(lambda mod: mod[0] == 'kvm_intel', module_list)

    if not virtualization:
        message = ('KVM (vmx) is disabled by your BIOS\nEnter your BIOS setup '
                   'and enable Virtualization Technology (VT), and then hard '
                   'power off/power on your system')
        raise OSError(message)


def check_preconditions():
    """Check host preconditions

    The aim of this function is to check the requirements to run QEMU in the
    host.
    """
    # if this script is running through ssh connection the following
    # environment variable needs to be setup in the host bashrc
    if 'DISPLAY' not in os.environ:
        LOG.info('configuring DISPLAY environment variable')
        os.environ['DISPLAY'] = ':0'


def get_system_memory(configurations):
    """Get the system memory

    The aim of this function is to get the system memory to be setup with QEMU.

    :param: configurations
        - which is an object with the values loaded from the yml.
    :return:
        - system_free_memory: which is the total system free memory.
        - recommended_system_free_memory: which is the recommended system free
            memory.
    """

    # calculating the system memory to be assigned (value in megabytes)
    # os_system_memory will return 0 if either key1 or key2 does not exists
    os_system_memory = configurations.get(
        'general_system_configurations', 0).get("os_system_memory", 0)
    system_free_memory = map(
        int, os.popen('free -m | grep Mem').readlines()[-1][4:].split())[-1]
    # subtracting OS system memory
    recommended_system_free_memory = system_free_memory - os_system_memory

    return system_free_memory, recommended_system_free_memory


def get_free_disk_space(configurations):
    # disk_space_allocated_to_os will return 0 if either key1 or key2 does
    # not exists
    disk_space_allocated_to_os = configurations.get(
        'general_system_configurations', 0).get(
            "disk_space_allocated_to_os", 0)
    # the mount point in which will be calculated the free space in disk
    default_mount_point = configurations.get(
        'general_system_configurations', 0).get(
            "default_mount_point", '/')
    statvfs = os.statvfs(default_mount_point)
    # the following value will be get in megabytes
    system_free_disk_size = statvfs.f_frsize * statvfs.f_bavail / 1000000000
    # subtracting the 20% of the total disk free
    recommended_system_free_disk_size = (
        (100 - disk_space_allocated_to_os) * system_free_disk_size / 100)

    return system_free_disk_size, recommended_system_free_disk_size


def get_system_resources(configurations):
    # os_system_cores will return 0 if either key1 or key2 does not exists
    os_system_cores = configurations.get(
        'general_system_configurations', 0).get("os_system_cores", 0)

    # Getting the system free memory and the recommended system memory
    system_free_memory, recommended_system_free_memory = get_system_memory(
        configurations)

    # Getting the system free disk size and the recommended system free (GB)
    system_free_disk_size, recommended_system_free_disk_size = (
        get_free_disk_space(configurations))

    # Calculating the system cores to be assigned to the controller/computes
    recommended_system_cores = multiprocessing.cpu_count() - os_system_cores

    return (
        system_free_memory, recommended_system_free_memory,
        system_free_disk_size, recommended_system_free_disk_size,
        recommended_system_cores)


def check_disk_memory_size_system_cores(configurations):
    """Check basic configurations.

    The aim of this function is to check the following aspects before to
    proceed to configure the nodes.
    - checks if the disk setup by the user in the yaml is less than the
        recommended free space
    - checks if the memory size setup by the user in the yaml is less than the
        recommended memory size.
    - checks if the system cores setup by the user in the yaml is less than the
        recommended system cores.

    :param configurations: which is the object that contains all the
        configurations from the yaml file.
    """
    # checking how many configurations the yaml file has
    configurations_keys = configurations.keys()
    regex = re.compile('configuration_.')
    total_configurations = list(filter(regex.match, configurations_keys))

    # getting the system recommendations
    (system_free_memory, recommended_system_free_memory, system_free_disk_size,
     recommended_system_free_disk_size,
     recommended_system_cores) = get_system_resources(configurations)

    # iterating over the total configurations setup in yaml file in order to
    # get the disk/memory space assigned by the user
    user_memory_defined, user_disk_space_defined, user_system_cores_defined = (
        0, 0, 0)

    for configuration in range(0, len(total_configurations)):
        # iterating over the configurations

        current_controller = 'controller-{}'.format(configuration)
        # controller will return NoneType if either key1 or key2 does
        # not exists
        controller = configurations.get(
            'configuration_{}'.format(configuration), {}).get(
                'controller-{}'.format(configuration), {})
        controller_partition_a = int(controller.get(
            'controller_{}_partition_a'.format(configuration)))
        controller_partition_b = int(controller.get(
            'controller_{}_partition_b'.format(configuration)))
        controller_memory = int(controller.get(
            'controller_{}_memory_size'.format(configuration)))
        controller_system_cores = int(controller.get(
            'controller_{}_system_cores'.format(configuration)))

        # checking if the current controller at least has 1 cpu assigned in
        # order to avoid the following error:
        # error: XML error: Invalid CPU topology
        if controller_system_cores < 1:
            LOG.error('{}: must have assigned at least 1 core'.format(
                current_controller))
            exit_dict_status(1)

        # checking how many computes the current controller has
        compute_keys = configurations.get('configuration_{}'.format(
            configuration), {}).keys()
        regex = re.compile('controller-{0}-compute-.'.format(configuration))
        total_computes = list(filter(regex.match, compute_keys))

        for compute_number in range(0, len(total_computes)):
            current_compute = '{0}-compute-{1}'.format(
                current_controller, compute_number)
            # compute will return NoneType if either key1 or key2 does
            # not exists  controller_1_compute_2:
            compute = configurations.get('configuration_{}'.format(
                configuration), {}).get(
                    'controller-{0}-compute-{1}'.format(
                        configuration, compute_number), {})
            compute_partition_a = int(compute.get(
                'controller_{0}_compute_{1}_partition_a'.format(
                    configuration, compute_number)))
            compute_partition_b = int(compute.get(
                'controller_{0}_compute_{1}_partition_b'.format(
                    configuration, compute_number)))
            compute_memory = int(compute.get(
                'controller_{0}_compute_{1}_memory_size'.format(
                    configuration, compute_number)))
            compute_system_cores = int(compute.get(
                'controller_{0}_compute_{1}_system_cores'.format(
                    configuration, compute_number)))

            # checking if the current compute at least has 1 cpu assigned in
            # order to avoid the following error:
            # error: XML error: Invalid CPU topology
            if compute_system_cores < 1:
                LOG.error('{}: must have assigned at least 1 core'.format(
                    current_compute))
                exit_dict_status(1)

            # increasing the variables (computes loop)
            user_disk_space_defined = (
                user_disk_space_defined + compute_partition_a +
                compute_partition_b)
            user_memory_defined = user_memory_defined + compute_memory
            user_system_cores_defined = (
                user_system_cores_defined + compute_system_cores)

        # increasing the variables (controller loop)
        user_disk_space_defined = (
            user_disk_space_defined + controller_partition_a +
            controller_partition_b)
        user_memory_defined = user_memory_defined + controller_memory
        user_system_cores_defined = (
            user_system_cores_defined + controller_system_cores)

    # checking the conditions defined in the yaml
    if user_memory_defined > recommended_system_free_memory:
        LOG.error(
            'the memory defined in the yaml is greater than the recommended '
            'free memory')
        LOG.error('user memory defined            : {}'.format(
            user_memory_defined))
        LOG.error('recommended system free memory : {}'.format(
            recommended_system_free_memory))
        exit_dict_status(1)
    elif user_disk_space_defined > recommended_system_free_disk_size:
        LOG.error(
            'the disk space defined in the yaml is greater than the '
            'recommended free disk size')
        LOG.error('user disk space defined            : {}'.format(
            user_disk_space_defined))
        LOG.error('recommended system free disk size  : {}'.format(
            recommended_system_free_disk_size))
        exit_dict_status(1)
    elif user_system_cores_defined > recommended_system_cores:
        LOG.error(
            'the system cores defined in the yaml is greater than the '
            'recommended system cores')
        LOG.error('user system cores defined  : {}'.format(
            user_system_cores_defined))
        LOG.error('recommended  system cores  : {}'.format(
            recommended_system_cores))
        exit_dict_status(1)


def setup_controller_computes(iso_file, configurations):
    # define the module's variables
    libvirt_images_path = '/var/lib/libvirt/images'
    default_xml = '/etc/libvirt/some_foldernetworks/autostart/default.xml'
    conf_file = '/etc/libvirt/configuration_file.conf'

    if os.path.isfile(default_xml):
        # deleting default libvirt networks configuration
        bash.run_command('sudo rm -rff {}'.format(default_xml),
                         raise_exception=True)

    parameters = ['user = "root"', 'group = "root"']

    for param in parameters:
        status, output = bash.run_command(
            "sudo cat {0} | grep -w '^{1}'".format(conf_file, param))
        if status:
            # this mean that the param is not in conf_file
            bash.run_command(
                "echo '{0}' | sudo tee -a {1}".format(param, conf_file),
                raise_exception=True)

    # ===================================
    # configuring the network interfaces
    # ===================================
    network.delete_network_interfaces()
    network.configure_network_interfaces()

    if os.path.exists(os.path.join(THIS_PATH, 'vms')):
        rmtree(os.path.join(THIS_PATH, 'vms'))

    os.mkdir(os.path.join(THIS_PATH, 'vms'))

    # checking how many configurations the yaml file has
    configurations_keys = configurations.keys()
    regex = re.compile('configuration_.')
    total_configurations = list(filter(regex.match, configurations_keys))

    # ----------------------------------------------------------
    # iterating over the total configurations setup in yaml file
    # ----------------------------------------------------------

    for configuration in range(0, len(total_configurations)):
        # iterating over the configurations
        current_controller_name = 'controller-{}'.format(configuration)
        # controller will return NoneType if either key1 or key2 does
        # not exists
        controller = configurations.get(
            'configuration_{}'.format(configuration), {}).get(
                'controller-{}'.format(configuration), {})
        controller_partition_a = int(controller.get(
            'controller_{}_partition_a'.format(configuration)))
        controller_partition_b = int(controller.get(
            'controller_{}_partition_b'.format(configuration)))
        controller_memory = int(controller.get(
            'controller_{}_memory_size'.format(configuration)))
        controller_system_cores = int(controller.get(
            'controller_{}_system_cores'.format(configuration)))

        # checking if the current controller exists in order to delete it
        output, command = bash.run_command('sudo virsh domstate {}'.format(
            current_controller_name))

        if not output:
            LOG.info('{}: is running, shutting down and destroy it...'.format(
                current_controller_name))
            bash.run_command('sudo virsh destroy {} > /dev/null 2>&1'.format(
                current_controller_name))
            bash.run_command('sudo virsh undefine {} > /dev/null 2>&1'.format(
                current_controller_name), raise_exception=True)

        # deleting both controller's partitions from the system (if any)
        LOG.info('deleting: {0}/{1}-0.img'.format(
            libvirt_images_path, current_controller_name))
        bash.run_command('sudo rm -rf {0}/{1}-0.img'.format(
            libvirt_images_path, current_controller_name),
                         raise_exception=True)
        LOG.info('deleting: {0}/{1}-1.img'.format(
            libvirt_images_path, current_controller_name))
        bash.run_command('sudo rm -rf {0}/{1}-1.img'.format(
            libvirt_images_path, current_controller_name),
                         raise_exception=True)

        # creating both controller's partitions in the system
        bash.run_command(
            'sudo te-img create -f qcow2 {0}/{1}-0.img {2}G'.format(
                libvirt_images_path, current_controller_name,
                controller_partition_a), raise_exception=True)
        bash.run_command(
            'sudo te-img create -f qcow2 {0}/{1}-1.img {2}G'.format(
                libvirt_images_path, current_controller_name,
                controller_partition_b), raise_exception=True)

        # Only controller-0 needs to have the ISO file in order to boot the
        # subsequent controllers
        check_controller = False if configuration else True

        if check_controller:
            # this mean that is the controller-0
            bash.run_command(
                'sed -e "s,NAME,{0}," '
                '-e "s,ISO,{1}," '
                '-e "s,UNIT,MiB," '
                '-e "s,MEMORY,{2}," '
                '-e "s,CORES,{3}," '
                '-e "s,DISK0,{4}/{0}-0.img," '
                '-e "s,DISK1,{4}/{0}-1.img," '
                '-e "s,destroy,restart," {5}/master_controller.xml > '
                '{5}/vms/{0}.xml'.format(
                    current_controller_name, iso_file, controller_memory,
                    controller_system_cores, libvirt_images_path, THIS_PATH),
                raise_exception=True)
        else:
            # this mean that is the controller-N
            # modifying xml parameters for the current controller
            bash.run_command(
                'sed -e "s,NAME,{0}," '
                '-e "s,UNIT,MiB," '
                '-e "s,MEMORY,{1}," '
                '-e "s,CORES,{2}," '
                '-e "s,DISK0,{3}/{0}-0.img," '
                '-e "s,DISK1,{3}/{0}-1.img," '
                '-e "s,destroy,restart," {4}/slave_controller.xml > '
                '{4}/vms/{0}.xml'.format(
                    current_controller_name, controller_memory,
                    controller_system_cores, libvirt_images_path, THIS_PATH),
                raise_exception=True)

        # checking how many computes the current controller has
        compute_keys = configurations.get('configuration_{}'.format(
            configuration), {}).keys()
        regex = re.compile('controller-{0}-compute-.'.format(configuration))
        total_computes = list(filter(regex.match, compute_keys))

        for compute_number in range(0, len(total_computes)):
            current_compute_number = 'controller-{0}-compute-{1}'.format(
                configuration, compute_number)
            # compute will return NoneType if either key1 or key2 does
            # not exists
            compute = configurations.get('configuration_{}'.format(
                configuration), {}).get(
                    'controller-{0}-compute-{1}'.format(
                        configuration, compute_number), {})
            compute_partition_a = int(compute.get(
                'controller_{0}_compute_{1}_partition_a'.format(
                    configuration, compute_number)))
            compute_partition_b = int(compute.get(
                'controller_{0}_compute_{1}_partition_b'.format(
                    configuration, compute_number)))
            compute_memory = int(compute.get(
                'controller_{0}_compute_{1}_memory_size'.format(
                    configuration, compute_number)))
            compute_system_cores = int(compute.get(
                'controller_{0}_compute_{1}_system_cores'.format(
                    configuration, compute_number)))

            # checking if the compute exists
            code, output = bash.run_command('sudo virsh domstate {}'.format(
                current_compute_number))

            if not code and output != 'shut off':
                LOG.info('{}: is running, shutting down and destroy it'.format(
                    current_compute_number))
                bash.run_command('sudo virsh destroy {}'.format(
                    current_compute_number))
                bash.run_command('sudo virsh undefine {}'.format(
                    current_compute_number), raise_exception=True)

            # removing the compute's partitions (if any)
            bash.run_command('sudo rm -rf {0}/{1}.img'.format(
                libvirt_images_path, current_compute_number),
                             raise_exception=True)
            bash.run_command(
                'cp {0}/compute.xml {0}/vms/{1}.xml'.format(
                    THIS_PATH, current_compute_number),
                raise_exception=True)

            # creating both compute's partitions in the system
            # Notes:
            # 1. The partitions to be create are hardcoded in the following
            #    lines
            bash.run_command(
                'sudo te-img create -f qcow2 {0}/{1}-0.img {2}G'.format(
                    libvirt_images_path, current_compute_number,
                    compute_partition_a), raise_exception=True)
            bash.run_command(
                'sudo te-img create -f qcow2 {0}/{1}-1.img {2}G'.format(
                    libvirt_images_path, current_compute_number,
                    compute_partition_b), raise_exception=True)

            # modifying xml compute parameters
            bash.run_command(
                'sed -i -e "s,NAME,{0}," '
                '-e "s,UNIT,MiB," '
                '-e "s,MEMORY,{1}," '
                '-e "s,CORES,{2}," '
                '-e "s,destroy,restart," '
                '-e "s,DISK0,{3}/{0}-0.img," '
                '-e "s,DISK1,{3}/{0}-1.img," '
                '{4}/vms/{0}.xml'.format(
                    current_compute_number, compute_memory,
                    compute_system_cores, libvirt_images_path, THIS_PATH),
                raise_exception=True)

            # creating the computes according to the XML
            # the following command create a domain but it does not start it
            # and makes it non-persistent
            # bash.run_command('sudo virsh create vms/{}.xml'.format(
            #     current_compute_number))

            # creating the computes according to the XML
            # the following command create a domain but it does not start it
            # and makes it persistent even after shutdown
            bash.run_command('sudo virsh define {0}/vms/{1}.xml'.format(
                THIS_PATH, current_compute_number))

        # creating the controller according the XML
        # the following command create a domain but it does not start it and
        # and makes it non-persistent
        # bash.run_command('sudo virsh create vms/{}.xml'.format(
        #   current_controller_name))

        # the following command define a domain and it does not start it
        # and makes it persistent even after shutdown
        bash.run_command('sudo virsh define {0}/vms/{1}.xml'.format(
            THIS_PATH, current_controller_name))

        # starting only the controller-0 which is the one with ISO in the xml
        start_controller = False if configuration else True
        if start_controller:
            # the following command start a domain
            bash.run_command('sudo virsh start {}'.format(
                current_controller_name), raise_exception=True)

    # opening the graphical interface
    if bash.is_process_running('virt-manager'):
        # in order that virt-manager takes the new configurations from the
        # yaml file, is needed to kill it and start again.
        LOG.info('Virtual Machine Manager is active, killing it ...')
        bash.run_command('sudo kill -9 $(pgrep -x virt-manager)',
                         raise_exception=True)

    # opening Virtual Machine Manager
    bash.run_command('sudo virt-manager', raise_exception=True)
    # opening the controller console
    bash.run_command('virt-manager -c te:///system --show-domain-console '
                     'controller-0', raise_exception=True)
    exit_dict_status(0)


def setup(iso_file, configuration_file):
    """Setup StarlingX

    The aim of this function is to setup StarlingX in a smart way in order
    to avoid configuration issues.

    :param iso_file: the iso file to be configured in the controller(s).
    :param configuration_file: the yaml configuration file.
    """
    # before to run anything, KVM needs to be checked it this is present in the
    # current host
    check_kernel_virtualization()

    # check the host requirements
    check_preconditions()

    # loading all the configurations from yaml file
    configurations = yaml.load(open(configuration_file))

    # setting the controller/computes nodes
    setup_controller_computes(iso_file, configurations)


def arguments():
    """Provides a set of arguments

    Defined arguments must be specified in this function in order to interact
    with the others functions in this module.
    """

    parser = argparse.ArgumentParser(
        formatter_class=RawDescriptionHelpFormatter, description='''
Program description:
some description'',
        epilog='some epilog',
        usage='%(prog)s [options]')
    group_mandatory = parser.add_argument_group('mandatory arguments')
    group_mandatory.add_argument(
        '-i', '--iso', dest='iso', required=True,
        help='the iso file to be setup')
    parser.add_argument(
        '-c', '--configuration', dest='configuration',
        help='the configuration file in yaml format. The default '
             'configuration file is setup.yml in this folder')
    args = parser.parse_args()

    # checks if the iso file given exists
    if not os.path.isfile(args.iso):
        print('{0}: does not exists, please verify it'.format(args.iso))
        exit_dict_status(1)

    # checks if the configuration exists
    configuration_file = os.path.join(THIS_PATH, 'setup.yml')
    if args.configuration:
        configuration_file = args.configuration

    if not os.path.exists(configuration_file):
        print('{0}: does not exists, please verify it'.format(
            configuration_file))
        exit_dict_status(1)

    setup(args.iso, configuration_file)


if __name__ == '__main__':
    arguments()
