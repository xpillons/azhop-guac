from typing import List, Optional

from hpc.autoscale.job.job import Job
from hpc.autoscale.node.node import Node

from guac.driver import GuacDriver

"""
max_run_res etc - group/user/project syntax
"""

class GuacEnvironment:
    def __init__(
        self,
        jobs: List[Job],
        scheduler_nodes: List[Node],
    ) -> None:
        self.jobs = jobs
        self.scheduler_nodes = scheduler_nodes

def from_driver(guac_driver: Optional[GuacDriver] = None) -> GuacEnvironment:
    guac_driver = guac_driver or GuacDriver()

    jobs = guac_driver.parse_jobs()
    scheduler_nodes = guac_driver.parse_scheduler_nodes()

    return GuacEnvironment(
        jobs=jobs,
        scheduler_nodes=scheduler_nodes,
    )
