import sys
from argparse import ArgumentParser
from typing import Dict, Iterable, List, Optional, Tuple

from hpc.autoscale import clilib
from hpc.autoscale.job.demandcalculator import DemandCalculator
from hpc.autoscale.job.driver import SchedulerDriver
from hpc.autoscale.job.job import Job
from hpc.autoscale.results import DefaultContextHandler
from hpc.autoscale.util import partition_single

from guac import environment
from guac.autoscaler import new_demand_calculator
from guac.environment import GuacEnvironment
from guac.driver import GuacDriver

from guac.database import GuacDatabase

class GUACCLI(clilib.CommonCLI):
    def __init__(self) -> None:
        clilib.CommonCLI.__init__(self, "guac")
        # lazily initialized
        self.__guac_env: Optional[GuacEnvironment] = None
        self.__driver: Optional[GuacDriver] = None

    def _initialize(self, command: str, config: Dict) -> None:
        pass

    def _driver(self, config: Dict) -> SchedulerDriver:
        if self.__driver is None:
            self.__driver = GuacDriver(GuacDatabase(config["guac"]))
        return self.__driver

    def _initconfig(self, config: Dict) -> None:
        pass

    def _initconfig_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--guac-config",
            default="/etc/guacamole/guacamole.properties",
            dest="guac__config_file",
        )
        parser.add_argument(
            "--guac-spool",
            default="/anfhome/guac-spool",
            dest="guac__spool_dir",
        )
        parser.add_argument(
            "--guac-vaultname",
            dest="guac__vaultname",
        )
        pass

    def _default_output_columns(
        self, config: Dict, cmd: Optional[str] = None
    ) -> List[str]:

        return config.get(
            "output_columns",
            [
                "name",
                "hostname",
                "guac_state",
                "job_ids",
                "state",
                "vm_size",
            ]
            + [
                "instance_id[:11]",
                "ctr@create_time_remaining",
                "itr@idle_time_remaining",
            ],
        )

    def _guac_env(self, guac_driver: GuacDriver) -> GuacEnvironment:
        if self.__guac_env is None:
            self.__guac_env = environment.from_driver(guac_driver)
        return self.__guac_env

    def _demand_calc(
        self, config: Dict, driver: SchedulerDriver
    ) -> Tuple[DemandCalculator, List[Job]]:
        guac_driver: GuacDriver = driver
        guac_env = self._guac_env(guac_driver)
        dcalc = new_demand_calculator(config, guac_env=guac_env, guac_driver=guac_driver)
        return dcalc, guac_env.jobs

    def _setup_shell_locals(self, config: Dict) -> Dict:
        """
        Provides read only interactive shell. type guachelp()
        in the shell for more information
        """
        ctx = DefaultContextHandler("[interactive-readonly]")

        guac_driver = GuacDriver()
        guac_env = self._guac_env(guac_driver)

        def guachelp() -> None:
            print("config               - dict representing autoscale configuration.")
            print("cli                  - object representing the CLI commands")
            print(
                "guac_env              - object that contains data structures for queues, resources etc"
            )
            print("jobs                 - dict of job id -> Autoscale Job")
            print(
                "scheduler_nodes      - dict of hostname -> node objects. These represent purely what"
                "                  the scheduler sees without additional booting nodes / information from CycleCloud"
            )
            print(
                "resource_definitions - dict of resource name -> GuacResourceDefinition objects."
            )
            print(
                "guac_driver         - GuacDriver object that interacts directly with Guacamole and implements"
                "                    Guac specific behavior for scalelib."
            )
            print(
                "demand_calc          - ScaleLib DemandCalculator - pseudo-scheduler that determines the what nodes are unnecessary"
            )
            print(
                "node_mgr             - ScaleLib NodeManager - interacts with CycleCloud for all node related"
                + "                    activities - creation, deletion, limits, buckets etc."
            )
            print("guachelp            - This help function")

        jobs_dict = partition_single(guac_env.jobs, lambda j: j.name)

        sched_nodes_dict = partition_single(
            guac_env.scheduler_nodes, lambda n: n.hostname
        )

        for snode in guac_env.scheduler_nodes:
            snode.shellify()

        guac_env.resource_definitions = clilib.ShellDict(guac_env.resource_definitions)

        demand_calc, _ = self._demand_calc(config, guac_driver)

        shell_locals = {
            "config": config,
            "cli": self,
            "ctx": ctx,
            "guac_env": guac_env,
            "jobs": clilib.ShellDict(jobs_dict, "j"),
            "scheduler_nodes": clilib.ShellDict(sched_nodes_dict),
            "resource_definitions": guac_env.resource_definitions,
            "guac_driver": guac_driver,
            "demand_calc": demand_calc,
            "node_mgr": demand_calc.node_mgr,
            "guachelp": guachelp,
        }

        return shell_locals

    def validate(self, config: Dict) -> None:
        """
        Best-effort validation of your Guac environment's compatibility with this autoscaler.
        """
        guac_driver = GuacDriver()
        guac_env = self._guac_env(guac_driver)

        exit = 0

        sys.exit(exit)


def main(argv: Iterable[str] = None) -> None:
    clilib.main(argv or sys.argv[1:], "guac", GUACCLI())


if __name__ == "__main__":
    main()
