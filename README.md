# Parallel-Executer
Executing commands across a fleet of servers is a usual activity for an SRE. Some commands like “uptime” can be executed in all nodes without any impact, where as some commands  like “service restart” require careful batching of servers to avoid any sort of potential downtime. Forease of explanation, let's call the former type of commands as “harmless-commands” and latter ones as “needs-caution-commands”. This script would execute a command across the maximum number of servers in parallel without any downtime. 
*Hostnames contain both rack and slot information.*
e.g. web-dc1-rack1-10.somecompany.com  => rack : rack1 , slot : 10
 **needs-caution-commands** :  At any given time, only one node from a rack should be running the command.


# Requirements:
  - Ensure python3, pip3 installed.
  - A file `hostfile.txt` containing list of hostname on which command is to be executer. 
  - Server running this script should be able to access all servers present in hostfile. If Not you can specify common private key file in .env file.
  - specify common user in .env file which is used for ssh.
  - If each hosts have diferrent config (for example: different user for each hosts) specify custom config per host in `custom_config.yaml` file

# How to Run:
  - pip3 install -r <path to requirements.txt file>
  - Ensure ssh related config is updated as specified under Requiremets
  - Please do check dotenv file to ensure you config is correct before running
  - python3 <path to executer.py file> -hf <path of file containing hostnames>
   -c <command to run> -ctype <command type only 2 choices available [harmless,needs-caution]>


### Demo
```sh
$ pip install -r requirements.txt
$ python code/executer.py -hf tests/test.txt -c uptime -ctype harmless
```
