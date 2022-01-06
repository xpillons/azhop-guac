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
# from pbspro.parser import PBSProParser, get_pbspro_parser, set_pbspro_parser
# from pbspro.pbscmd import PBSCMD
# from pbspro.resource import read_resource_definitions


class GUACCLI(clilib.CommonCLI):
    def __init__(self) -> None:
        clilib.CommonCLI.__init__(self, "guac")
        # bootstrap parser
        #set_pbspro_parser(PBSProParser({}))
        #self.pbscmd = PBSCMD(get_pbspro_parser())
        # lazily initialized
        self.__guac_env: Optional[GuacEnvironment] = None
        self.__driver: Optional[GuacDriver] = None

    def _initialize(self, command: str, config: Dict) -> None:
        pass
        # resource_definitions = read_resource_definitions(self.pbscmd, config)
        # set_pbspro_parser(PBSProParser(resource_definitions))
        # self.pbscmd = PBSCMD(get_pbspro_parser())

    def _driver(self, config: Dict) -> SchedulerDriver:
        if self.__driver is None:
            self.__driver = GuacDriver(GuacDatabase(config["guac"]))#self.pbscmd)
        return self.__driver

    def _initconfig(self, config: Dict) -> None:
        pass

    def _initconfig_parser(self, parser: ArgumentParser) -> None:
        pass

    def _default_output_columns(
        self, config: Dict, cmd: Optional[str] = None
    ) -> List[str]:
        # driver = self._driver(config)
        # env = self._guac_env(driver)
        # resource_columns = []
        # resource_columns = sorted(resource_columns)

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
#            + resource_columns
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
#            print("queues               - dict of queue name -> PBSProQueue object")

            print("jobs                 - dict of job id -> Autoscale Job")
            print(
                "scheduler_nodes      - dict of hostname -> node objects. These represent purely what"
                "                  the scheduler sees without additional booting nodes / information from CycleCloud"
            )
            print(
                "resource_definitions - dict of resource name -> GuacResourceDefinition objects."
            )
            # print(
            #     "default_scheduler    - PBSProScheduler object representing the default scheduler."
            # )
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

        # try to make the key "15" instead of "15.hostname" if only
        # a single submitter was in use
        # num_scheds = len(set([x.name.split(".", 1)[-1] for x in pbs_env.jobs]))
        # if num_scheds == 1:
        #     jobs_dict = partition_single(pbs_env.jobs, lambda j: j.name.split(".")[0])
        # else:
        jobs_dict = partition_single(guac_env.jobs, lambda j: j.name)

        sched_nodes_dict = partition_single(
            guac_env.scheduler_nodes, lambda n: n.hostname
        )

#        pbs_env.queues = clilib.ShellDict(pbs_env.queues)

        for snode in guac_env.scheduler_nodes:
            snode.shellify()

        guac_env.resource_definitions = clilib.ShellDict(guac_env.resource_definitions)

        demand_calc, _ = self._demand_calc(config, guac_driver)

        shell_locals = {
            "config": config,
            "cli": self,
            "ctx": ctx,
            "guac_env": guac_env,
#            "queues": pbs_env.queues,
            "jobs": clilib.ShellDict(jobs_dict, "j"),
            "scheduler_nodes": clilib.ShellDict(sched_nodes_dict),
            "resource_definitions": guac_env.resource_definitions,
#            "default_scheduler": guac_env.default_scheduler,
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
        # sched = pbs_env.default_scheduler
        # if not sched:
        #     print("Could not find a default server.", file=sys.stderr)
        #     sys.exit(1)

        exit = 0

        # for attr in ["ungrouped", "group_id"]:
        #     if attr not in sched.resources_for_scheduling:
        #         print(
        #             "{} is not defined for line 'resources:' in {}/sched_priv.".format(
        #                 attr, sched.sched_priv
        #             )
        #             + " Please add this and restart PBS"
        #         )
        #         exit = 1

        # if sched.node_group_key and not sched.node_group_enable:
        #     print(
        #         "node_group_key is set to '{}' but node_group_enable is false".format(
        #             sched.node_group_key
        #         ),
        #         file=sys.stderr,
        #     )
        #     exit = 1
        # elif not sched.node_group_enable:
        #     print(
        #         "node_group_enable is false, so MPI/parallel jobs may not work if multiple placement groups are created.",
        #         file=sys.stderr,
        #     )
        #     exit = 1

        # if not sched.only_explicit_psets:
        #     print(
        #         "only_explicit_psets should be set to true in your sched_config if you are using MPI or colocated jobs.",
        #         file=sys.stderr,
        #     )
        #     exit = 1
        # if not sched.do_not_span_psets:
        #     print(
        #         "do_not_span_psets should be set to true in your sched_config if you are using MPI or colocated jobs.",
        #         file=sys.stderr,
        #     )
        #     exit = 1

        sys.exit(exit)


def main(argv: Iterable[str] = None) -> None:
    clilib.main(argv or sys.argv[1:], "guac", GUACCLI())


if __name__ == "__main__":
    main()
