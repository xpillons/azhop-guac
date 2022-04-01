from argparse import ArgumentParser
import os
import sys
import time
from threading import Lock
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

import hpc.autoscale.hpclogging as logging
from hpc.autoscale.results import DefaultContextHandler, register_result_handler
from hpc.autoscale.util import json_load

from guac.autoscaler import autoscale_guac
from guac.spooler import init_spooler, update_status, process_file, process_spool_dir

mutex = Lock()

class Handler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config

    def on_created(self, event):
        # Take any action here when a file is first created.
        print("Received created event - {}.".format(event.src_path))
        mutex.acquire()
        try:
            print("Processing command")
            process_file(self.config, event.src_path)
            print("Finished processing command")
            update_status(self.config)
            print("Status updated")
        finally:
            mutex.release()


def main() -> int:
#    logging.initialize_logging()

    ctx_handler = register_result_handler(DefaultContextHandler("[initialization]"))

    parser = ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="Path to autoscale config.", required=True
    )
    args = parser.parse_args()
    config_path = os.path.expanduser(args.config)

    if not os.path.exists(config_path):
        print("{} does not exist.".format(config_path), file=sys.stderr)
        return 1

    config = json_load(config_path)
    logging.initialize_logging(config)

    init_spooler(config)

    process_spool_dir(config)

    event_handler = Handler(config)
    observer = PollingObserver()
    observer.schedule(event_handler, os.path.join(config["guac"]["spool_dir"], "commands"))
    observer.start()

    while True:
        mutex.acquire()
        try:
            autoscale_guac(config, ctx_handler=ctx_handler)
            update_status(config)
        except Exception as e:
            logging.exception(str(e))
        finally:
            mutex.release()
        time.sleep(10)

    #    observer.stop()
    #    observer.join()

    return 0


if __name__ == "__main__":
    sys.exit(main())