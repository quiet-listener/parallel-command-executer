#!/bin/python
import os,argparse
import logging,logging.config
import yaml
from queue import PriorityQueue
from pssh.clients.native import ParallelSSHClient
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')  # get dotenv file path
load_dotenv(dotenv_path)  # load env from dotenv file

''' 
get logger conf path and initialize logger with that conf.
Using 2 separate log file for stdout and code error 

'''
logger_path = os.path.join(os.path.dirname(__file__), 'logger.conf') 
logging.config.fileConfig(logger_path)
logger_info = logging.getLogger('info')
logger_error = logging.getLogger('error')

# import from env else set value to None
MAX_PARALLEL_CONCURRENCY = int(os.environ.get("MAX_PARALLEL_CONCURRENCY"))
PORT = int(os.environ.get("PORT")) if os.environ.get("PORT") else None
NUM_RETRIES = int(os.environ.get("NUM_RETRIES")) if os.environ.get("NUM_RETRIES") else None
RETRY_DELAY = int(os.environ.get("RETRY_DELAY")) if os.environ.get("RETRY_DELAY") else None
PSSH_TIMEOUT = int(os.environ.get("PSSH_TIMEOUT")) if os.environ.get("PSSH_TIMEOUT") else None
PSSH_SUDO = os.environ.get("PSSH_SUDO")
PSSH_USER = os.environ.get("PSSH_USER")
PSSH_PKEY = os.environ.get("PSSH_PKEY")
PSSH_PERHOSTCONF = os.environ.get("PSSH_PERHOSTCONF")

'''
load_perhost_conf module : tries to load per host conf file into PSSH_PERHOSTCONF if provided
'''
def load_perhost_conf():
    global PSSH_PERHOSTCONF
    if PSSH_PERHOSTCONF and is_file_valid(PSSH_PERHOSTCONF):
        with open(PSSH_PERHOSTCONF, 'r') as ystream:
            try:
                PSSH_PERHOSTCONF=yaml.safe_load(ystream)
            except yaml.YAMLError as exc:
                logger_error.critical(exc, extra={'host': os.uname()[1], 'exit_code': '1', 'command_name': "yaml load"})
                print("yaml loading failed! check error logs")
    else:
        PSSH_PERHOSTCONF=None

'''
pssh_execute module : general module being used to execute commands in parallel through pss.
and prints 
    1- exit_status on stdout 
    2- program output in cmd_stdout.log file
Note: `pool_size=MAX_PARALLEL_CONCURRENCY` is provided to ensure at max MAX_PARALLEL_CONCURRENCY parallel commands are executed
'''

def pssh_execute(hosts,cmd):
    try:
        client = ParallelSSHClient(hosts=hosts, user=PSSH_USER, port=PORT, num_retries=NUM_RETRIES,         host_config=PSSH_PERHOSTCONF, retry_delay=RETRY_DELAY, timeout=PSSH_TIMEOUT, pool_size=MAX_PARALLEL_CONCURRENCY, pkey=PSSH_PKEY)
        output = client.run_command(command=cmd, sudo=PSSH_SUDO, stop_on_errors=False)
        client.join(output)
        for host, host_output in output.items():
            if host_output.exception :
                print("{} : {} : exception while connecting host. Check executer.log file for error log".format(
                    host, cmd))
                logger_error.critical(host_output.exception, extra={'host': host, 'exit_code': '1', 'command_name': cmd})
            else:
                if host_output.exit_code > 0:
                    print("{} : {} : execution Failed with exit status {} check cmd_stdout.log file for error log".format(host,cmd,host_output.exit_code))
                    logger_info.error(''.join(host_output.stderr), extra={'host': host, 'exit_code': host_output.exit_code, 'command_name': cmd})
                else:
                    print("{} : {} : execution Succeeded with exit status {} check cmd_stdout.log file for output log".format(host, cmd, host_output.exit_code))  
                    logger_info.info(''.join(host_output.stdout), extra={'host': host, 'exit_code': host_output.exit_code, 'command_name': cmd})
    except Exception as e:
        logger_error.critical(e, extra={'host': os.uname()[1], 'exit_code': '1', 'command_name': cmd})
        print("{} : {} : exception in Code. Check executer.log file for error log".format(
            os.uname()[1], cmd))

'''
 execute_caution module : ensures that at any given time, only one node from a rack should be running the command. For this I have created buckets on rack to pick one node from each bucket while making list of hosts for parallel excution. Also it ensure that no more than MAX_PARALLEL_CONCURRENCY nodes can execute the command in parallel. To minimize `number of  parallel calls in batch i.e. number of calls to pssh_execute module` I have used the priority Queue to ensure racks with max no. of nodes are selected for parallel execution

'''


def execute_caution(host_file,cmd):
    bucket_info={}
    # create bucket on rack with values as list of nodes in that rack
    with open(host_file) as hosts:
        for host in hosts:
            temp_host=host.split(".",1)[0]
            temp_rack=temp_host.split("-rack",1)[1]
            rs_info=temp_rack.split("-")
            if rs_info[0] not in bucket_info:
                bucket_info[rs_info[0]]=[host.strip()]
            else:
                bucket_info[rs_info[0]].append(host.strip())
    # Priority Queue to ensure minimum calls to pssh_execute modules are made
    max_buckets=PriorityQueue()
    # taken priority as negative of len of nodes in rack for max heap
    for tpls in [(-len(bucket_info[key]), key) for key in bucket_info.keys()]:
        max_buckets.put(tpls)

    while(not max_buckets.empty()):
        top_nodes=[]
        # get nodes till either bucket is empty or MAX_PARALLEL_CONCURRENCY 
        while (not max_buckets.empty()) and (len(top_nodes) < MAX_PARALLEL_CONCURRENCY):
            top_nodes.append(max_buckets.get())
        n_hosts=[ bucket_info[key].pop() for _,key in top_nodes]
        top_nodes=[ (c+1,key) for c,key in top_nodes]
        for c,k in top_nodes:
            if c<0:
                max_buckets.put((c,k))
        #pssh_execute(n_hosts, cmd)


'''
execute_harmless module :  just sends list of hosts to be executed to pssh_execute module
Note: pss_execute module makes sure that at max MAX_PARALLEL_CONCURRENCY parallel connections are made to hosts
'''

def execute_harmless(host_file,cmd):
    with open(host_file) as hosts:
        n_hosts=[ n_host.strip() for n_host in hosts]
        pssh_execute(n_hosts,cmd)
        
'''
 is_file_valid module : checks if path is valid and file exists
'''
def is_file_valid(filename):
    return os.path.isfile(filename)

'''
main module : takes commandline args and invokes module for parallel ssh as per harmless or need-caution 
Note: in arg parse provided nargs to get any space separated string in arguments
'''

def main():
    parser = argparse.ArgumentParser(description='Parallel Remote Program Executer...')
    parser.add_argument("-hf", "--hostFile", nargs='+', required=True,
                        help="Filename with list of hosts")
    parser.add_argument("-c", "--command", nargs='+', required=True,
                        help="Command to be executed")
    parser.add_argument("-ctype", "--commandType", choices=['harmless', 'needs-caution'], required=True,
                        help="Flag to indicate whether  a command is “harmless” or “needs-caution” type")
    arg=parser.parse_args();
    host_file=' '.join(arg.hostFile)
    cmd=' '.join(arg.command)
    ctype=arg.commandType
    load_perhost_conf()
    if not is_file_valid(host_file):
        print(host_file+" not found")
        exit(1);
    if ctype=="harmless":
        execute_harmless(host_file,cmd)
    else:
        execute_caution(host_file,cmd)
    

if __name__=="__main__": main()

