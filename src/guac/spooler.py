import os, sys, json
from argparse import ArgumentParser
from typing import Dict, Any, Optional

from hpc.autoscale.util import json_load
import hpc.autoscale.hpclogging as logging

from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential, _credentials

from guac.database import GuacDatabase, GuacConnectionStates, GuacConnectionAttributes

_spool_dir="/anfhome/guac-spool"
_exit_code = 0
_credential = None
_logger = None

_KVUri = ""

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
    guacdb = GuacDatabase(config["guac"])

    # list all files in spool dir
    command_dir = os.path.join(_spool_dir, "commands")
    if not os.path.exists(command_dir):
        os.makedirs(command_dir)
    for filename in os.listdir(command_dir):
        if filename.endswith(".json"):
            full_filename = os.path.join(command_dir, filename)
            _logger.info("Processing file %s", full_filename)
            with open(full_filename) as f:
                data = json.load(f)
                connection_name = os.path.splitext(filename)[0]

                # Create a new connection
                if data["command"] == "create":
                    _logger.info("Processing command %s", data["command"])
                    connection_id = guacdb.create_new_connection(connection_name, data["user"], get_user_password(data["user"]), data["domain"], data["queue"])
                    update_status_file(connection_name, str(connection_id), GuacConnectionStates.Queued)

                # Delete connection
                elif data["command"] == "delete":
                    _logger.info("Processing command %s", data["command"])
                    guacdb.delete_connection(data["connection_id"], data["user"])
                    delete_status(connection_name)
                # Unknown command
                else:
                    _logger.error("Unknown command %s", data["command"])
                    _exit_code = 1
                os.remove(full_filename)

# Retrieve user password from the keyvault
def get_user_password(username: str) -> str:
    global _credential

    client = SecretClient(vault_url=_KVUri, credential=_credential)
    retrieved_secret = client.get_secret(f"{username}-password")
    return retrieved_secret.value

def delete_status(connection_name: int) -> None:
    global _exit_code
    global _spool_dir

    status_dir = os.path.join(_spool_dir, "status")
    status_filename = os.path.join(status_dir, "{}.json".format(connection_name))
    if os.path.exists(status_filename):
        os.remove(status_filename)

def update_status_file(connection_name: str, connection_id: str, status: str, hostname: Optional[str] = "") -> None:
    global _exit_code
    global _spool_dir

    status_dir = os.path.join(_spool_dir, "status")

    if not os.path.exists(status_dir):
        os.makedirs(status_dir)

    status_filename = os.path.join(status_dir, "{}.json".format(connection_name))
    with open(status_filename, "w") as f:
        f.write("{")
        f.write("\"status\": \"{}\"".format(status))
        f.write(",\"connection_id\": \"{}\"".format(connection_id))
        f.write(",\"hostname\": \"{}\"".format(hostname))
        f.write("}")

def update_status(
        config: Dict[str, Any],
) -> None:
    global _exit_code
    global _spool_dir

    _logger.info("Update status")
    guacdb = GuacDatabase(config["guac"])
    #TODO : Add garbage collection of status files. Remove status files that are not in the database.

    response: Dict = guacdb.get_connections()

    for record in response:
        update_status_file(str(record["connection_name"]), str(record["connection_id"]), record[GuacConnectionAttributes.Status], record["hostname"])



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

    _credential = DefaultAzureCredential()
    keyVaultName = config["guac"]["vaultname"]
    _KVUri = f"https://{keyVaultName}.vault.azure.net"

    logging.initialize_logging(config)
    _logger = logging.getLogger("guac_spooler")
    _spool_dir = config["guac"]["spool_dir"]
    process_spool_dir(config)
    update_status(config)

    return _exit_code

if __name__ == "__main__":
    main()