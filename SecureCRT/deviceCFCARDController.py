# $language = "Python"
# $interface="1.0"
import sys, os, logging, time, csv, re, io, random
from itertools import chain

objTab = crt.GetScriptTab()
objTab.Screen.Synchronous = True
objTab.Screen.IgnoreEscape = True
logging.basicConfig(filename="LOG.log", level=logging.DEBUG)
logging.basicConfig(format='%(levelname)s %(asctime)s: %(message)s', level=logging.DEBUG,
                    datefmt='%m/%d/%Y %I:%M:%S %p')
logging.info("This log file generated by Upgrade Controller.py")
wait_for_seconds = 15
prompt_string_of_main_screen = "$"
results_path_all_devices = r"Results/"
file_name = "Device List.csv"
result_file_name = "Device-Upgrade-Control.csv"
ssh_users = ["admin"]
ssh_users_passwords = ["password"]


class GetterSetter:
    def __init__(self, item=0):
        self._item = item

    def get_item(self):
        return self._item

    def set_item(self, variable):
        self._item = variable


returned_value = GetterSetter()


def clear_known_hosts():
    """Cleaning existing IP addresses"""
    command = "rm -rf .ssh/known_hosts\r"
    objTab.Screen.Send(command)
    objTab.Screen.WaitForString(prompt_string_of_main_screen)


def command_sender(command, prompt_string,time_gap=4, objTab=objTab):
    objTab.Screen.Send(command + "\r")
    objTab.Screen.WaitForString(prompt_string,time_gap)


def read_command_output(command, prompt_string, time_gap=4, objTab=objTab):
    objTab.Screen.Send(command + "\r")
    objTab.Screen.WaitForString(command, time_gap)
    command_output = objTab.Screen.ReadString(prompt_string)
    command_output = command_output.split("\r")
    return command_output

def get_devices_from_csv():
    the_devices = list()
    last_name_ip_address = ""
    if os.path.exists(result_file_name):
        with open(result_file_name,"r") as csv_result_file:
            reader = csv.reader(csv_result_file,delimiter="\n")
            last_device = [row for row in reader][-1]
            last_name_ip_address = ",".join(last_device[0].split(",")[:2])
                
    with open(file_name,"r") as csv_file:
        reader = csv.reader(csv_file,delimiter="\n")
        for row in reader:
            the_devices.extend(row)
    cut_index = [the_devices.index(item) for item in the_devices if item.startswith("NE Name")][0]+1
    the_devices = [item.replace("\t",",") for item in the_devices[cut_index:]]
    
    if not last_name_ip_address == "":
        cut_index = [the_devices.index(item) for item in the_devices if last_name_ip_address in item][0]+1
        the_devices = [item.replace("\t",",") for item in the_devices[cut_index:]]
    return the_devices[:]

def csv_writer(data):
    header = ["Management IP", "NE Name", "NE District", "NE Version", 
              "MPU Memory (Master)","Utilization" ,"MPU Memory (Slave)", "Utilization" ,"CFCARD Total", "CFCARD Free" ,
              "CFCARD2 Total", "CFCARD2 Free", "SLAVECFCARD Total" , "SLAVECFCARD Free" , "SLAVECFCARD2 Total" , "SLAVECFCARD2 Free"
            ]
    
    if not os.path.exists(results_path_all_devices):
        os.mkdir(results_path_all_devices)

    if not os.path.exists(results_path_all_devices + result_file_name):
        with open(results_path_all_devices + result_file_name,"ab") as writer_obj:
            writer = csv.writer(writer_obj)
            writer.writerow(header)
    with open(results_path_all_devices + result_file_name,"ab") as writer_obj:
        writer = csv.writer(writer_obj)
        writer.writerows(data)

def find_given_device(device_name):
    the_devices = list()
    with open(file_name,"r") as csv_file:
        reader = csv.reader(csv_file,delimiter="\n")
        for row in reader:
            the_devices.extend(row)
    cut_index = [the_devices.index(item) for item in the_devices if item.startswith(device_name)][0]
    intended_device = the_devices[cut_index]
    return intended_device

def wait_if_password_succeed(device_prompt_string, device_ip, ssh_user, ssh_user_password,objTab):
    global returned_value
    wait_for_device_prompt_strings = [device_prompt_string, "The password needs to be changed. Change now? [Y/N]:",
                                      "Password:", "Enter password:"]
    command = ssh_user_password + "\r"
    objTab.Screen.Send(command)
    wait_if_prompt = objTab.Screen.WaitForStrings(wait_for_device_prompt_strings, wait_for_seconds)

    if wait_if_prompt == 1:
        # Success Login return ok with set-get method
        command = ""
        command_sender(command, device_prompt_string, objTab=objTab)
        returned_value.set_item("OK")

    elif wait_if_prompt == 2:
        # Success Login but first send "N" letter
        command = "N"
        command_sender(command, device_prompt_string, objTab=objTab)
        returned_value.set_item("OK")

    elif wait_if_prompt == 3 or wait_if_prompt == 4:
        # Device current ssh user is not exists or password is wrong
        returned_value.set_item("Mismatch")

    else:
        # Something went wrong or the 15 second timer is exceeded
        returned_value.set_item("NOK")


def wait_if_ssh_succeed(device_prompt_string, device_ip, ssh_user, ssh_user_password,objTab):
    global returned_value
    wait_for_password_strings = ["Password:", "Enter password:",
                                 "Warning: Permanently added " + "'" + device_ip + "'" + " (RSA) to the list of known hosts.ssh_rsa_verify: RSA modulus too small: 512 < minimum 768 bitskey_verify failed for server_host_key"]
    command = "yes\r"
    objTab.Screen.Send(command)
    wait_if_password = objTab.Screen.WaitForStrings(wait_for_password_strings, wait_for_seconds)

    if wait_if_password == 1 or wait_if_password == 2:
        wait_if_password_succeed(device_prompt_string, device_ip, ssh_user, ssh_user_password,objTab)
    elif wait_if_password == 3:
        returned_value.set_item("SSH-RSA-Key")
    else:
        returned_value.set_item("NOK")


def connect_device(device_prompt_string, device_ip, ssh_user, ssh_user_password,objTab):
    global returned_value
    wait_for_ssh_connection_strings = ["Are you sure you want to continue connecting (yes/no)?",
                                       "ssh: connect to host " + str(device_ip) + " port 22: Connection refused"
                                       ]
    command = "ssh -l " + ssh_user + " " + device_ip + "\n"
    objTab.Screen.Send(command)
    wait_if_ssh = objTab.Screen.WaitForStrings(wait_for_ssh_connection_strings, wait_for_seconds)

    if wait_if_ssh == 1:
        wait_if_ssh_succeed(device_prompt_string, device_ip, ssh_user, ssh_user_password,objTab)
    elif wait_if_ssh == 2:
        returned_value.set_item("SSH-Refused")


def exit_device(objTab):
    command = "quit"
    command_sender(command, prompt_string_of_main_screen,objTab=objTab)
    command = chr(13)
    command_sender(command, prompt_string_of_main_screen,objTab=objTab)


def connect_to_host(device_ip,device_prompt_string,objTab):
    global returned_value

    ping_command = "ping " + str(device_ip)
    ping_command_output = read_command_output(ping_command, prompt_string_of_main_screen, time_gap=wait_for_seconds,objTab=objTab)
    ping_command_output = " ".join(ping_command_output)
    if "is alive" in ping_command_output:
        # Device alive
        for item in range(len(ssh_users)):

            clear_known_hosts()
            ssh_user = ssh_users[item]
            ssh_user_password = ssh_users_passwords[item]
            connect_device(device_prompt_string, device_ip, ssh_user, ssh_user_password,objTab)
            am_i_connected = returned_value.get_item()

            if am_i_connected == "Mismatch":
                command = "\x03"
                command_sender(command, prompt_string_of_main_screen)
                continue
            else:
                return am_i_connected
    else:
        # Device not alive
        command = "\x03"
        command_sender(command, prompt_string_of_main_screen)
        return "Ping Failed"
    return "Users are not valid"

def output_organizer(command_output,device_name):
    command_output = filter(None, command_output)
    command_output = [item.strip() for item in command_output if not device_name in item 
                          and not all(x=="-" for x in item)]
    command_output = [str(item) for item in command_output]
    command_output = filter(None, command_output)
    return command_output

def total_and_free_spaces(card_memory):
    return card_memory[:card_memory.rfind("total")-1], card_memory[card_memory.find("(")+1:card_memory.rfind("free")-1]

def Main():
    global objTab

    device_list = get_devices_from_csv()
    data = list()
    for device in device_list:
        
        device_name,device_ip, version, district = device.split(",")
        device_prompt_string = ">"

        try:
            device_district = district.split("/")[2].strip()
        except:
            device_district = "ROOT"

        am_i_conn = connect_to_host(device_ip,device_prompt_string,objTab=objTab)

        if am_i_conn == "OK":

            command = " s 0 t"
            command_sender(command,device_prompt_string)
            
            command = "display health"
            health_information = read_command_output(command,device_prompt_string)
            health_information = output_organizer(health_information,device_name)
            health_information = " ".join(" ".join(health_information).split())
            
            master_mpu_ipu_regex = "MPU\(Master\)+\s+\d+%\s+\d+%+\s+\S+|IPU\(Master\)+\s+\d+%\s+\d+%+\s+\S+"
            slave_mpu_ipu_regex = "MPU\(Slave\)+\s+\d+%\s+\d+%+\s+\S+|IPU\(Slave\)+\s+\d+%\s+\d+%+\s+\S+"
            
            health_information_master = re.findall(master_mpu_ipu_regex,health_information)
            health_information_slave = re.findall(slave_mpu_ipu_regex,health_information)
            
            try:
                _, cpu_mpu_master_util, memory_mpu_master_util, memory_mpu_master = health_information_master[0].split(" ")
                _, cpu_mpu_slave_util, memory_mpu_slave_util, memory_mpu_slave = health_information_slave[0].split(" ")
                memory_mpu_master_used,memory_mpu_master_total = memory_mpu_master.split("/")
                memory_mpu_slave_used,memory_mpu_slave_total = memory_mpu_slave.split("/")
            except:
                _, cpu_mpu_master_util, memory_mpu_master_util, memory_mpu_master = None, "NA", "Error", "Error"
                _, cpu_mpu_slave_util, memory_mpu_slave_util, memory_mpu_slave = None, "NA", "Error", "Error"
                memory_mpu_master_used=memory_mpu_master_total = "Error"
                memory_mpu_slave_used=memory_mpu_slave_total="Error"
            

            memory_card_size = lambda x: x[-1]
            command = "dir cfcard:/"
            cfcard_contents = read_command_output(command,device_prompt_string)
            cfcard_contents = output_organizer(cfcard_contents,device_name)
            cfcard_size = memory_card_size(cfcard_contents)
            
            command = "dir slave#cfcard:/"
            slavecfcard_contents = read_command_output(command,device_prompt_string)
            slavecfcard_contents = output_organizer(slavecfcard_contents,device_name)
            slavecfcard_size = memory_card_size(slavecfcard_contents)
            
            try:
                cfcard_total, cfcard_free = total_and_free_spaces(cfcard_size)
                slavecfcard_total, slavecfcard_free = total_and_free_spaces(slavecfcard_size)
            except:
                cfcard_total = cfcard_free = slavecfcard_total = slavecfcard_free ="Error"
            
            if not "NetEngine 8000" in version:
                command = "dir cfcard2:/"
                cfcard2_contents = read_command_output(command,device_prompt_string)
                cfcard2_contents = output_organizer(cfcard2_contents,device_name)
                cfcard2_size = memory_card_size(cfcard2_contents)
                
                command = "dir slave#cfcard2:/"
                slavecfcard2_contents = read_command_output(command,device_prompt_string)
                slavecfcard2_contents = output_organizer(slavecfcard2_contents,device_name)
                slavecfcard2_size = memory_card_size(slavecfcard2_contents)
            
                try:
                    cfcard_2_total, cfcard_2_free = total_and_free_spaces(cfcard2_size)
                    slavecfcard2_total, slavecfcard2_free = total_and_free_spaces(slavecfcard2_size)
                except:
                    cfcard_2_total = cfcard_2_free = slavecfcard2_total = slavecfcard2_free ="Error"
            else:
                
                cfcard_2_total = cfcard_2_free = slavecfcard2_total = slavecfcard2_free = "Not Exists for M14"
            
            data.append([device_ip, device_name, device_district, version, 
                        memory_mpu_master_total, memory_mpu_master_util, memory_mpu_slave_total, memory_mpu_slave_util,
                        cfcard_total, cfcard_free, cfcard_2_total, cfcard_2_free, slavecfcard_total, slavecfcard_free,
                        slavecfcard2_total, slavecfcard2_free
                         ])
            

        elif am_i_conn == "NOK" or am_i_conn == "SSH-RSA-Key" or am_i_conn == "SSH-Refused":
            # SSH Releated Failure
            logging.warning("Connection failed to host " + device_name)
        elif am_i_conn == "Ping Failed":
            logging.warning("Ping failed to host " + device_name)
        elif am_i_conn == "Users are not valid":
            logging.critical("Users are not valid for the host " + device_name)
            command = "\x03"
            command_sender(command, prompt_string_of_main_screen)
        csv_writer(data)
        data = list()
        exit_device(objTab)

Main()
logging.shutdown()
