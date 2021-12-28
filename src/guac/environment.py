from typing import Dict, List, Optional

from hpc.autoscale.hpctypes import Hostname
from hpc.autoscale.job.job import Job
from hpc.autoscale.node.node import Node

from guac.driver import GuacDriver
# from pbspro.pbscmd import PBSCMD
# from pbspro.pbsqueue import PBSProQueue
# from pbspro.resource import PBSProResourceDefinition
# from pbspro.scheduler import PBSProScheduler


"""
max_run_res etc - group/user/project syntax
"""


class GuacEnvironment:
    def __init__(
        self,
        # schedulers: Dict[Hostname, PBSProScheduler],
        # queues: Dict[str, PBSProQueue],
        # resource_definitions: Dict[str, PBSProResourceDefinition],
        jobs: List[Job],
        scheduler_nodes: List[Node],
        # pbscmd: PBSCMD,
    ) -> None:
#        self.schedulers = schedulers
#        self.active_schedulers = [x for x in self.schedulers.values() if x.is_active]
#        self.default_scheduler = None
        # if self.active_schedulers:
        #     default_scheds = [x for x in self.active_schedulers if x.is_default]
        #     if default_scheds:
        #         self.default_scheduler = default_scheds[0]
#        self.queues = queues
#        self.resource_definitions = resource_definitions
        self.jobs = jobs
        self.scheduler_nodes = scheduler_nodes
#        self.pbscmd = pbscmd

    # def delete_nodes(self, nodes: List[Node]) -> None:
    #     hostnames = [n.hostname_or_uuid for n in nodes]
    #     self.scheduler_nodes = [n for n in self.scheduler_nodes if n !=]


def from_driver(guac_driver: Optional[GuacDriver] = None) -> GuacEnvironment:
    guac_driver = guac_driver or GuacDriver()

#    schedulers = guac_driver.read_schedulers()
    # default_schedulers = [s for s in schedulers.values() if s.is_default]
    # default_scheduler = default_schedulers[0]

#    queues = guac_driver.read_queues(default_scheduler.resource_state.shared_resources)

    jobs = guac_driver.parse_jobs() #queues, default_scheduler.resources_for_scheduling)
    scheduler_nodes = guac_driver.parse_scheduler_nodes()

    return GuacEnvironment(
        # schedulers=schedulers,
        # queues=queues,
#        resource_definitions=guac_driver.resource_definitions,
#        pbscmd=guac_driver.pbscmd,
        jobs=jobs,
        scheduler_nodes=scheduler_nodes,
    )
