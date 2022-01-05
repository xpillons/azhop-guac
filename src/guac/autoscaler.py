import os
import sys
from argparse import ArgumentParser
from typing import Any, Dict, List, Optional
from guac.database import GuacDatabase

import hpc.autoscale.job.driver
import hpc.autoscale.hpclogging as logging
from hpc.autoscale.job import demandprinter
from hpc.autoscale.job.demand import DemandResult
from hpc.autoscale.job.demandcalculator import new_demand_calculator
from hpc.autoscale.results import DefaultContextHandler, register_result_handler
from hpc.autoscale.util import SingletonLock, json_load
from hpc.autoscale.node.nodehistory import NodeHistory
from hpc.autoscale.job.demandcalculator import DemandCalculator
from hpc.autoscale.job import demandcalculator as dcalclib
from hpc.autoscale.node.nodemanager import new_node_manager

from guac.driver import GuacDriver
from guac.environment import GuacEnvironment
from guac import environment as envlib

_exit_code = 0

def autoscale_guac(
    config: Dict[str, Any],
    guac_env: Optional[GuacEnvironment] = None,
    guac_driver: Optional[GuacDriver] = None,
    ctx_handler: Optional[DefaultContextHandler] = None,
    node_history: Optional[NodeHistory] = None,
    dry_run: bool = False,
) -> DemandResult:
    global _exit_code

    assert not config.get("read_only", False)
    if dry_run:
        logging.warning("Running guac autoscaler in dry run mode")
        # allow multiple instances
        config["lock_file"] = None
        # put in read only mode
        config["read_only"] = True

    guacdb = GuacDatabase(config["guac"])
    # interface to guac, generally by cli
    if guac_driver is None:
        # allow tests to pass in a mock
        guac_driver = GuacDriver(guacdb)

    if guac_env is None:
        guac_env = envlib.from_driver(guac_driver)

    guac_driver.initialize()

    config = guac_driver.preprocess_config(config)

    logging.debug("Driver = %s", guac_driver)

    demand_calculator = calculate_demand(config, guac_env, guac_driver, ctx_handler, node_history)

    failed_nodes = demand_calculator.node_mgr.get_failed_nodes()
    guac_driver.handle_failed_nodes(failed_nodes)

    demand_result = demand_calculator.finish()

    if ctx_handler:
        ctx_handler.set_context("[joining]")

    # details here are that we pass in nodes that matter (matched) and the driver figures out
    # which ones are new and need to be added
    joined = guac_driver.add_nodes_to_cluster(
        [x for x in demand_result.compute_nodes if x.exists]
    )

    guac_driver.handle_post_join_cluster(joined)

    if ctx_handler:
        ctx_handler.set_context("[scaling]")

    # bootup all nodes. Optionally pass in a filtered list
    if demand_result.new_nodes:
        if not dry_run:
            demand_calculator.bootup()

    if not dry_run:
        demand_calculator.update_history()

    # we also tell the driver about nodes that are unmatched. It filters them out
    # and returns a list of ones we can delete.
    idle_timeout = int(config.get("idle_timeout", 300))
    boot_timeout = int(config.get("boot_timeout", 3600))
    logging.fine("Idle timeout is %s", idle_timeout)

    unmatched_for_5_mins = demand_calculator.find_unmatched_for(at_least=idle_timeout)
    timed_out_booting = demand_calculator.find_booting(at_least=boot_timeout)

    # I don't care about nodes that have keep_alive=true
    timed_out_booting = [n for n in timed_out_booting if not n.keep_alive]

    timed_out_to_deleted = []
    unmatched_nodes_to_delete = []

    if timed_out_booting:
        logging.info(
            "The following nodes have timed out while booting: %s", timed_out_booting
        )
        timed_out_to_deleted = guac_driver.handle_boot_timeout(timed_out_booting) or []

    if unmatched_for_5_mins:
        logging.info("unmatched_for_5_mins %s", unmatched_for_5_mins)
        unmatched_nodes_to_delete = (
            guac_driver.handle_draining(unmatched_for_5_mins) or []
        )

    nodes_to_delete = []
    for node in timed_out_to_deleted + unmatched_nodes_to_delete:
        if node.assignments:
            logging.warning(
                "%s has jobs assigned to it so we will take no action.", node
            )
            continue
        nodes_to_delete.append(node)

    if nodes_to_delete:
        try:
            logging.info("Deleting %s", [str(n) for n in nodes_to_delete])
            delete_result = demand_calculator.delete(nodes_to_delete)

            if delete_result:
                # in case it has anything to do after a node is deleted (usually just remove it from the cluster)
                guac_driver.handle_post_delete(delete_result.nodes)
        except Exception as e:
            _exit_code = 1
            logging.warning("Deletion failed, will retry on next iteration: %s", e)
            logging.exception(str(e))

    print_demand(config, demand_result, log=not dry_run)

    return demand_result


def new_demand_calculator(
    config: Dict,
    guac_env: Optional[GuacEnvironment] = None,
    guac_driver: Optional["GuacDriver"] = None,
    ctx_handler: Optional[DefaultContextHandler] = None,
    node_history: Optional[NodeHistory] = None,
    singleton_lock: Optional[SingletonLock] = None,
) -> DemandCalculator:
    if guac_driver is None:
        guac_driver = GuacDriver()

    if guac_env is None:
        guac_env = envlib.from_driver(guac_driver)

    if node_history is None:
        node_history = guac_driver.new_node_history(config)

    # keep it as a config
    node_mgr = new_node_manager(config, existing_nodes=guac_env.scheduler_nodes)
    guac_driver.preprocess_node_mgr(config, node_mgr)
    singleton_lock = singleton_lock or guac_driver.new_singleton_lock(config)
    assert singleton_lock

    demand_calculator = dcalclib.new_demand_calculator(
        config,
        node_mgr=node_mgr,
        node_history=node_history,
        singleton_lock=singleton_lock,  # it will handle the none case,
        existing_nodes=guac_env.scheduler_nodes,
    )

    ccnode_id_added = False

    for bucket in demand_calculator.node_mgr.get_buckets():

        # ccnodeid will almost certainly not be defined. It just needs
        # to be defined once, so we will add a default for all nodes
        # the first time we see it is missingg
        if "ccnodeid" not in bucket.resources and not ccnode_id_added:
            hpc.autoscale.job.driver.add_ccnodeid_default_resource(
                demand_calculator.node_mgr
            )
            ccnode_id_added = True

    return demand_calculator


def calculate_demand(
    config: Dict,
    guac_env: GuacEnvironment,
    guac_driver: GuacDriver,
    ctx_handler: Optional[DefaultContextHandler] = None,
    node_history: Optional[NodeHistory] = None,
) -> DemandCalculator:

    demand_calculator = new_demand_calculator(
        config, guac_env, guac_driver, ctx_handler, node_history
    )
    # Check if connection is used
    for job in guac_env.jobs:
        if len(job.executing_hostnames) > 0:
            continue
        # if job.metadata.get("job_state") == "running":
        #     continue

        if ctx_handler:
            ctx_handler.set_context("[job {}]".format(job.name))
        demand_calculator.add_job(job)

    return demand_calculator


def print_demand(
    config: Dict,
    demand_result: DemandResult,
    output_columns: Optional[List[str]] = None,
    output_format: Optional[str] = None,
    log: bool = False,
) -> None:
    # and let's use the demand printer to print the demand_result.
    if not output_columns:
        output_columns = config.get(
            "output_columns",
            [
                "name",
                "hostname",
                "job_ids",
                "exists",
                "required",
                "managed",
                "vm_size",
                "memory",
                "vcpu_count",
                "state",
                "create_time_remaining",
                "idle_time_remaining",
            ],
        )

    if "all" in output_columns:  # type: ignore
        output_columns = []

    output_format = output_format or "table"

    demandprinter.print_demand(
        output_columns,
        demand_result,
        output_format=output_format,
        log=log,
    )
    return demand_result


def new_driver(config: Dict) -> "GuacDriver":
    import importlib

    guac_config = config.get("guac", {})

    driver_expr = guac_config.get("driver", "guac.driver.new_driver")

    if "." not in driver_expr:
        raise BadDriverError(driver_expr)

    module_expr, func_or_class_name = driver_expr.rsplit(".", 1)

    try:
        module = importlib.import_module(module_expr)
    except Exception as e:
        logging.exception(
            "Could not load module %s. Is it in the"
            + " PYTHONPATH environment variable? %s",
            str(e),
            sys.path,
        )
        raise

    func_or_class = getattr(module, func_or_class_name)
    return func_or_class(config)


class BadDriverError(RuntimeError):
    def __init__(self, bad_expr: str) -> None:
        super().__init__()
        self.bad_expr = bad_expr
        self.message = str(self)

    def __str__(self) -> str:
        return (
            "Expected guac.driver=module.func_name"
            + " or guac.driver=module.class_name. Got {}".format(self.bad_expr)
        )

    def __repr__(self) -> str:
        return str(self)


def main() -> int:
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

    autoscale_guac(config, ctx_handler=ctx_handler)

    return _exit_code


if __name__ == "__main__":
    sys.exit(main())