import os, sys, json, base64, datetime, pwd
from argparse import ArgumentParser
from typing import Dict, Any, Optional
from pathlib import Path

from hpc.autoscale.util import json_load
import hpc.autoscale.hpclogging as logging

from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential, _credentials

from guac.database import GuacDatabase, GuacConnectionStates, GuacConnectionAttributes

_spool_dir="/anfhome/guac-spool"
_exit_code = 0
_credential = None
_logger = None
_domain = "hpc.azure"
_KVUri = ""


def process_file(config, full_filename):
    _logger.info("Processing file %s", full_filename)
    filename = os.path.basename(full_filename)
    with open(full_filename) as f:
        try:
            data = json.load(f)
        except:
            _logger.warning("Failed parse command, deleting file")
            os.remove(full_filename)
            return

        path = Path(full_filename)
        connection_name = os.path.splitext(filename)[0]
        user = path.owner()
        # Create a new connection
        if data["command"] == "create":
            guacdb = GuacDatabase(config["guac"])
            _logger.info("Create connection to user %s on nodearray %s", user, data["queue"])
            # Check if the connection already exists
            record = guacdb.get_connection_by_name(connection_name)
            if len(record) == 0:
                password = get_user_password(user)
                if password is not None:
                    connection_id = guacdb.create_new_connection(connection_name, user, password, _domain, data["queue"], data["walltime"])
                    status = GuacConnectionStates.Queued
                else:
                    status = GuacConnectionStates.Failed
                    connection_id = -1
                    _logger.error("User %s password not found", user)
                update_status_file(connection_name, str(connection_id), status, user, queuename=data["queue"], walltime=data["walltime"], jobname=data["queue"])
            else:
                _logger.info("Connection %s already exists, skipping", connection_name)

        # Delete connection
        elif data["command"] == "delete":
            guacdb = GuacDatabase(config["guac"])
            record = guacdb.get_connection_by_name(connection_name)
            if len(record) > 0:
                connection_id = record[0][0]
                _logger.info("Delete connection %s for user %s", connection_id, user)
                guacdb.delete_connection(connection_id, user)
            else:
                _logger.info("Connection %s does not exist, skipping", connection_name)
            delete_status(connection_name)

        # Unknown command
        else:
            _logger.error("Unknown command %s", data["command"])

        os.remove(full_filename)


#
# for each files in the $SPOOL_DIR/commands directory
#    Read the file
#    Parse the file
#       If Command == "create"
#          Create a new connection
#          Create the status file
#       If Command == "delete"
#          Delete the connection
#          Delete the status file
#     Drop the file
def process_spool_dir(
        config: Dict[str, Any],
) -> None:
    global _exit_code
    global _spool_dir

    _logger.info("Processing spool directory %s", _spool_dir)

    # list all files in spool dir
    command_dir = os.path.join(_spool_dir, "commands")
    if not os.path.exists(command_dir):
        os.makedirs(command_dir)
    for filename in os.listdir(command_dir):
        process_file(config, os.path.join(command_dir, filename))

# Retrieve user password from the keyvault
def get_user_password(username: str) -> str:
    global _credential
    secret = None

    try:
        client = SecretClient(vault_url=_KVUri, credential=_credential)
        retrieved_secret = client.get_secret(f"{username.replace('.','')}-password")
        secret = retrieved_secret.value
    except Exception as e:
        _logger.error("Secret %s-password not found", username)
        logging.exception(str(e))

    return secret

def delete_status(connection_name: str) -> None:
    global _exit_code
    global _spool_dir

    status_dir = os.path.join(_spool_dir, "status")
    status_filename = os.path.join(status_dir, "{}.json".format(connection_name))
    if os.path.exists(status_filename):
        os.remove(status_filename)

def update_status_file(connection_name: str, connection_id: str, status: str, username: str, queuename: str, walltime: str, jobname: Optional[str] = "job", hostname: Optional[str] = "unknown", starttime: Optional[str]="0") -> None:
    global _exit_code
    global _spool_dir

    status_dir = os.path.join(_spool_dir, "status")

    if not os.path.exists(status_dir):
        os.makedirs(status_dir)

    if status == GuacConnectionStates.Queued:
        hostname = "unknown"

    data = "{}\0c\0mysql".format(connection_id)
    encodedBytes = base64.b64encode(data.encode("utf-8"))
    client_id = str(encodedBytes, "utf-8")

    status_filename = os.path.join(status_dir, "{}.json".format(connection_name))
    _logger.info("Writing connection status file %s", status_filename)
    with open(status_filename, "w") as f:
        f.write("{")
        f.write("\"status\": \"{}\"".format(status))
        f.write(",\"connection_id\": \"{}\"".format(connection_id))
        f.write(",\"user\": \"{}\"".format(username))
        f.write(",\"queuename\": \"{}\"".format(queuename))
        f.write(",\"jobname\": \"{}\"".format(jobname))
        f.write(",\"hostname\": \"{}\"".format(hostname))
        f.write(",\"client_id\": \"{}\"".format(client_id))
        f.write(",\"walltime\": \"{}\"".format(walltime))
        if starttime != "0":
            f.write(",\"startime\": \"{}\"".format(int(starttime)))
        else:
            f.write(",\"startime\": \"0\"")
        f.write("}")

def delete_session(connection_name: str, username: str) -> None:
    command_dir = os.path.join(_spool_dir, "commands")
    filename = os.path.join(command_dir, "{}.json".format(connection_name))

    _logger.info("Writing delete file %s", filename)
    with open(filename, "w") as f:
        f.write("{ \"command\": \"delete\" }")
    
    uid = pwd.getpwnam(username).pw_uid
    _logger.info("Update file %s with uid", filename, username)
    os.chown(filename, uid)

def update_status(
        config: Dict[str, Any],
) -> None:
    global _exit_code
    global _spool_dir

    _logger.info("Updating connections status")

    status_dir = os.path.join(_spool_dir, "status")
    if not os.path.exists(status_dir):
        os.makedirs(status_dir)

    old_status_files = set([f for f in os.listdir(status_dir) if os.path.isfile(os.path.join(status_dir, f))])
    
    guacdb = GuacDatabase(config["guac"])
    #TODO : Add garbage collection of status files. Remove status files that are not in the database.

    response: Dict = guacdb.get_connections()

    status_files = set()
    for record in response:
        status_files.add(str(record["connection_name"])+".json")
        update_status_file(str(record["connection_name"]), str(record["connection_id"]), record[GuacConnectionAttributes.Status], queuename=record[GuacConnectionAttributes.NodeArray], walltime=record[GuacConnectionAttributes.Walltime], starttime=record[GuacConnectionAttributes.StartTime], jobname=record[GuacConnectionAttributes.NodeArray], hostname=record["hostname"], username=record["username"])
        now = datetime.datetime.now().timestamp()
        start = int(record[GuacConnectionAttributes.StartTime])
        elapsed_time = int(now - start)
        if elapsed_time > int(record[GuacConnectionAttributes.Walltime]):
            _logger.info("Elapsed time reach for job %s - delet session", str(record["connection_id"]))
            delete_session(record["connection_name"], record["username"])

    _logger.info("Old status files:")
    _logger.info(old_status_files)
    _logger.info("New status files:")
    _logger.info(status_files)
    for old_file in old_status_files.difference(status_files):
        _logger.info("Deleting file: "+old_file)
        os.remove(os.path.join(status_dir, old_file))

def init_spooler(config):
    global _spool_dir
    global _credential
    global _KVUri
    global _logger

    _credential = DefaultAzureCredential()
    keyVaultName = config["guac"]["vaultname"]
    _KVUri = f"https://{keyVaultName}.vault.azure.net"

    logging.initialize_logging(config)
    _logger = logging.getLogger("guac_spooler")
    _spool_dir = config["guac"]["spool_dir"]

def main() -> int:
    parser = ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="Path to autoscale config.", required=True
    )
    global _spool_dir
    global _credential
    global _KVUri
    global _logger

    args = parser.parse_args()
    config_path = os.path.expanduser(args.config)

    if not os.path.exists(config_path):
        print("{} does not exist.".format(config_path), file=sys.stderr)
        return 1

    config = json_load(config_path)

    init_spooler(config)

    # TODO : Dynamically retrieve the domain 
    process_spool_dir(config)
    update_status(config)

    return _exit_code

if __name__ == "__main__":
    main()
