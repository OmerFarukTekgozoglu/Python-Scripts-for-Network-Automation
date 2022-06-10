from netmiko import ConnectHandler
import sys,os,time,logging,re,io,csv
from multiprocessing.dummy import Pool as ThreadPool
from itertools import chain
logging.basicConfig(filename = "log.log", level=logging.DEBUG, format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
from contextlib import contextmanager

result_filename = "Result.txt"
util_result_filename = "Utilization Results.txt"
device_list = "Devices.csv"

header = [
        "NE Name",
        "Management IP",
        "Region",
        "NE Type",
        "Version",
        "Total Slot",
        "Used Slot",
        "Total GE Port",
        "Used GE Port",
        "Free GE Port",
        "Total 10G Port",
        "Used 10G Port",
        "Free 10G Port",
        "Total 50G Port",
        "Used 50G Port",
        "Free 50G Port",
        "Total 100G Port",
        "Used 100G Port",
        "Free 100G Port",
        ]

class Device:
    M14 = "14"
    X8 = "8"
    X3 = "3"
    NE9000 = "8"
    DEFAULT = "8"

@contextmanager
def fileWriter(*args):
    
    try:
        result_file = open(*args)
        yield result_file
    except Exception as e:
        logging.info("An exception happened {}".format(e))
    finally:
        result_file.close()

def get_devices():
    devices = list()
    last_device = ""
    if os.path.exists(result_filename):
        with open(result_filename, "r") as csv_file:
            reader = csv.reader(csv_file,delimiter="\n")
            last_output = [row for row in reader][-1]
            last_device = ",".join(last_output[0].split(",")[:2])

    with open(device_list, "r") as csv_file:
        reader=csv.reader(csv_file,delimiter="\n")
        for row in reader:
            devices.extend(row)
    header_index = [devices.index(item) for item in devices if item.startswith("NE Name")][0]+1
    devices = [item.replace("\t",",") for item in devices]
    
    devices_for_return = devices[header_index:]
    if not last_device == "":
        cut_index = [devices_for_return.index(item) for item in devices_for_return if item.startswith(last_device)][0]+1
        devices_for_return = devices_for_return[cut_index:]
        
    devices_dict = {}
    for line in devices_for_return:
        device_info = line.strip().split(",")
        device = {"ip":device_info[1],
                  "version":device_info[2],
                  "region":device_info[3],
                  "ne_type":device_info[4],
                  "device_type":"huawei",
                  "fast_cli":"True"
                  }
        devices_dict[device["ip"]] = device
        
    return devices_dict

def count_interfaces(output):
    ge_100_regex = "^(?!50\|100GE)100GE\S+\s+[a-z|*]+\s+[a-z|*]+|(?<=\s)100GE\S+\s+[a-z|*]+\s+[a-z|*]+"
    ge_50_100_regex = "50\|100GE\S+\s+[a-z|*]+\s+[a-z|*]+"
    ge_10_regex = "(?<=\s)GigabitEthernet\S+(?:\(10G\))\s+[a-z|*]+\s+[a-z|*]\S+|(?<=\s)XGigabitEthernet\S+\s+[a-z|*]+\s+[a-z|*]\S+|GigabitEthernet\S+(?:\(100M\))\s+[a-z|*]+\s+[a-z|*]\S+"
    ge_regex = "(?<=\s)GigabitEthernet(?!0\/0\/0)\S+(?<!\(10G\))(?<!\(100M\))\s+[a-z|*]+\s+[a-z|*]\S+"
    
    ge_total = re.findall(ge_regex,output,re.MULTILINE)
    ge10_total = re.findall(ge_10_regex, output,re.MULTILINE)
    ge100_total = re.findall(ge_100_regex, output,re.MULTILINE)
    ge50_total = re.findall(ge_50_100_regex, output,re.MULTILINE)
    
    up_counter = lambda geX_list: [_.split()[1] for _ in geX_list].count("up") if geX_list != [] else "-"
    down_counter = lambda geX_list,used: len(geX_list)-used if geX_list != [] else "-"
    
    ge_used = up_counter(ge_total)
    ge10_used = up_counter(ge10_total)
    ge50_used = up_counter(ge50_total)
    ge100_used = up_counter(ge100_total)
    
    ge_free = down_counter(ge_total,ge_used)
    ge10_free = down_counter(ge10_total,ge10_used)
    ge50_free = down_counter(ge50_total,ge50_used)
    ge100_free = down_counter(ge100_total,ge100_used)
    
    return len(ge_total),ge_used,ge_free,len(ge10_total),ge10_used,ge10_free,len(ge50_total),ge50_used,ge50_free,len(ge100_total),ge100_used,ge100_free

def count_lpu_pic(output):
    lpu_pic_regex = "\d+\s+LPU|\d+\s+PIC"
    used_slots = re.findall(lpu_pic_regex,output)
    return len(used_slots)

def interface_usage(output,uplinks):
    
    interface_utilization_regex = "(?:GigabitEthernet|100GE|XGigabitEthernet)(?!0\/0\/0).+"

    interface_util = re.findall(interface_utilization_regex, output, re.MULTILINE)

    interface_utilizations = list()
    for _ in interface_util:
        interface_utilizations.append(re.split("\s+",_)[:-2])

    for interface in uplinks:
        for idx,_ in enumerate(interface_utilizations):
            dummy = _[0].replace("(10G)","")
            if interface == dummy:
                interface_utilizations[idx][0] = "(uplink) " + interface_utilizations[idx][0]

    return interface_utilizations

def config_worker(device):
    
    print("-"*5+ "Connection to device {0}, username={1}".format(device["ip"],device["username"]))

    result_dict = dict()

    version = device.pop('version')
    region = device.pop('region')
    ne_type = device.pop("ne_type")

    try:
        region = region.split("/")[2].strip()
    except:
        region = "ROOT"

    result_dict["region"] = region
    result_dict["version"] = version
    
    net_connect = ConnectHandler(**device)

    net_connect.send_command("screen-length 0 temporary", expect_string = "[#/?>]")

    device_prompt = net_connect.find_prompt()
    
    cmd = "display device"
    output = net_connect.send_command(cmd, expect_string=device_prompt, delay_factor=3)
    
    used_slots = count_lpu_pic(output)
    if "NE40E-X3" in ne_type:
        total_slots = Device.X3
    elif "NetEngine 8000 M14" in ne_type:
        total_slots = Device.M14
    else:
        total_slots = Device.DEFAULT
    
    cmd = "display interface brief main"
    output = net_connect.send_command(cmd, expect_string=device_prompt, delay_factor=3)

    ge_total,ge_used,ge_free,ge10_total,ge10_used,ge10_free,ge50_total,ge50_used,ge50_free,ge100_total,ge100_used,ge100_free = count_interfaces(output)

    cmd = "display isis interface"
    isis_output = net_connect.send_command(cmd, expect_string=device_prompt, delay_factor=3)

    interface_regex = "(?:GigabitEthernet|100GE|XGigabitEthernet|Eth-Trunk|GE)\S+"
    uplink_interfaces = re.findall(interface_regex,isis_output,re.MULTILINE)

    uplinks = list()

    for interface in uplink_interfaces:
        if interface.startswith("GE"):
            uplinks.append(interface.replace("GE","GigabitEthernet"))

        elif interface.startswith("100GE"):
            uplinks.append(interface)

        elif interface.startswith("Eth-Trunk"):
            if "." in interface:
                interface = interface[:interface.find(".")]
            interface = interface[len("Eth-Trunk"):]
            
            cmd = "display eth-trunk " + interface
            lag_interface = net_connect.send_command(cmd,expect_string=device_prompt,delay_factor=3)

            interface_regex = "(?:GigabitEthernet|100GE|XGigabitEthernet)\S+"
            lag_interface_list = list(set(re.findall(interface_regex,lag_interface,re.MULTILINE)))

            uplinks.extend(lag_interface_list)

    interface_utilizations = interface_usage(output,uplinks)

    result_dict["sysname"] = device_prompt.replace("<","").replace(">","")
    result_dict["mgmt_ip"] = device["ip"]
    print("-"*5+ "Writing results of {} into {}".format(result_dict["mgmt_ip"],result_filename))
    
    if not os.path.exists(result_filename):
        with fileWriter(result_filename, "a+") as writerObj:
            writerObj.write(",".join(header))
            writerObj.write("\n")
    with fileWriter(result_filename,"a+") as writerObj:
        line = ",".join([
                       result_dict["sysname"],
                       result_dict["mgmt_ip"],
                       result_dict["region"],
                       "{}".format(ne_type),
                       result_dict["version"],
                       "{}".format(total_slots),
                       "{}".format(used_slots),
                       "{}".format(ge_total),
                       "{}".format(ge_used),
                       "{}".format(ge_free),
                       "{}".format(ge10_total),
                       "{}".format(ge10_used),
                       "{}".format(ge10_free),
                       "{}".format(ge50_total),
                       "{}".format(ge50_used),
                       "{}".format(ge50_free),
                       "{}".format(ge100_total),
                       "{}".format(ge100_used),
                       "{}".format(ge100_free),
                       "\n"
                       ])
        writerObj.write(line)

    print("-"*5+ "Writing interface util. results of {} into {}".format(result_dict["mgmt_ip"],result_filename))
    if not os.path.exists(util_result_filename):
        with fileWriter(util_result_filename, "a+") as writerObj:
            writerObj.write("NE Name,Interface,PHY,Protocol,InUti,OutUti")
            writerObj.write("\n")
    with fileWriter(util_result_filename,"a+") as writerObj:
        writerObj.writelines(result_dict["sysname"]+","+",".join(line)+"\n" for line in interface_utilizations)
    
    net_connect.disconnect()  

if __name__ == "__main__":
    
    all_devices = get_devices()

    print("There are totally {} devices!".format(len(all_devices)))

    user = str(input("Enter username: ")).strip() or "admin"
    password = str(input("Enter password: ")).strip() or "12345"
    num_of_threads = int(input("Enter thread size: ")) or 5
    
    config_worker_param_list = []
    for ipaddr,device in all_devices.items():
        device["username"]=user
        device["password"]=password
        device["global_delay_factor"]=5
        config_worker_param_list.append(device)
        
    start_time = time.time()

    threads = ThreadPool(num_of_threads)
    results = threads.map(config_worker, config_worker_param_list)
    
    threads.close()
    threads.join()
    
    end_time = time.time()
    
    print("Script worked for {}".format(end_time-start_time))
    
    logging.shutdown()