import datetime
import socket

from typing import Dict, List, Optional, Set, Tuple

from hpc.autoscale import hpclogging as logging
from hpc.autoscale.job.driver import SchedulerDriver
from hpc.autoscale.node.node import Node
from hpc.autoscale.job.job import Job
from hpc.autoscale.node.constraints import SharedResource
from hpc.autoscale.node.nodemanager import NodeManager
from hpc.autoscale.job.schedulernode import SchedulerNode

from guac.database import GuacDatabase, GuacConnectionStates, GuacConnectionAttributes

class GuacDriver(SchedulerDriver):
    """
    The main interface for interacting with Guacamole and also
    overrides the generic SchedulerDriver with Guac specific behavior.
    """

    def __init__(
        self,
        guacdb: Optional[GuacDatabase] = None,
        down_timeout: int = 300,
    ) -> None:
        super().__init__("guac")
        self.guacdb = guacdb
        self.__read_only_resources: Optional[Set[str]] = None
        self.__jobs_cache: Optional[List[Job]] = None
        self.__scheduler_nodes_cache: Optional[List[Node]] = None
        self.__resource_definitions = None
        self.down_timeout = down_timeout
        self.down_timeout_td = datetime.timedelta(seconds=self.down_timeout)

    @property
    def resource_definitions(self) -> Dict:
        return self.__resource_definitions

    @property
    def read_only_resources(self) -> Set[str]:
        if not self.__read_only_resources:
            self.__read_only_resources = set(
                [r.name for r in self.resource_definitions.values() if r.read_only]
            )
        return self.__read_only_resources

    def initialize(self) -> None:
        """
        Placeholder for subclasses to customize initialization
        By default, we make sure that the ccnodeid exists
        """
        pass

    def preprocess_config(self, config: Dict) -> Dict:
        """
        Placeholder for subclasses to customize config dynamically
        """
        return config

    def preprocess_node_mgr(self, config: Dict, node_mgr: NodeManager) -> None:
        """
        We add a default resource to map group_id to node.placement_group
        """
        super().preprocess_node_mgr(config, node_mgr)

    # TODO : To be tested
    def handle_failed_nodes(self, nodes: List[Node]) -> List[Node]:
        to_delete = []
        to_drain = []
        now = datetime.datetime.now()

        for node in nodes:

            if node.state == "Failed":
                node.closed = True
                to_delete.append(node)
                continue

            if node.resources.get("ccnodeid"):
                logging.fine(
                    "Attempting to delete %s but ccnodeid is not set yet.", node
                )
                continue

            job_state = node.metadata.get("pbs_state", "")
            if "down" in job_state:
                node.closed = True
                if "offline" in job_state:
                    to_delete.append(node)
                else:
                    if self._down_long_enough(now, node):
                        to_drain.append(node)

        if to_drain:
            logging.info("Draining down nodes: %s", to_drain)
            self.handle_draining(to_drain)

        if to_delete:
            logging.info("Deleting down,offline nodes: %s", to_drain)
            return self.handle_post_delete(to_delete)
        return []

    def _down_long_enough(self, now: datetime.datetime, node: Node) -> bool:
        last_state_change_time_str = node.metadata.get("last_state_change_time")

        if last_state_change_time_str:
            last_state_change_time = datetime.datetime.strptime(
                last_state_change_time_str, "%a %b %d %H:%M:%S %Y"
            )
            delta = now - last_state_change_time
            if delta > self.down_timeout_td:
                return True
            else:
                seconds_remaining = (delta - self.down_timeout_td).seconds
                logging.debug(
                    "Down node %s still has %s seconds before setting to offline",
                    node,
                    seconds_remaining,
                )

        return False

    def add_nodes_to_cluster(self, nodes: List[Node]) -> List[Node]:
        self.initialize()

        ret = []
        for node in nodes:
            if not node.hostname:
                continue

            # TODO: Add a parameter to turn on reverse DNS testing
            # if not self._validate_reverse_dns(node):
            #     logging.fine(
            #         "%s still has a hostname that can not be looked via reverse dns. This should repair itself.",
            #         node,
            #     )
            #     continue

            if not node.resources.get("ccnodeid"):
                logging.info(
                    "%s is not managed by CycleCloud, or at least 'ccnodeid' is not defined. Ignoring",
                    node,
                )
                continue
            try:
                if len(node.assignments):
                    job_id=int(next(iter(node.assignments)))
                    # If connection is already running, skip it
                    attributes = self.guacdb.get_connection_attributes(job_id)
                    if attributes[GuacConnectionAttributes.Status] == GuacConnectionStates.Running:
                        continue
                    if attributes[GuacConnectionAttributes.NodeId] == node.resources.get("ccnodeid"):
                        logging.info(
                            "%s is already assigned to job %s, skipping",
                            node,
                            job_id,
                        )
                        continue

                    self.guacdb.assign_connection_to_host(job_id, node.hostname)
                    node_status = getattr(node, "state")
                    # TODO : add node status in the connection status
                    if node_status == "Ready":
                        self.guacdb.update_connection_status(job_id, GuacConnectionStates.Running)
                        self.guacdb.update_connection_nodeid(job_id, node.resources["ccnodeid"])
                    ret.append(node)
            except Exception as e:
                logging.error(
                    "Could not assign %s to connection: %s. Will attempt next cycle",
                    node,
                    e,
                )

        return ret

    def handle_post_join_cluster(self, nodes: List[Node]) -> List[Node]:
        return nodes

    def handle_boot_timeout(self, nodes: List[Node]) -> List[Node]:
        return nodes

    def handle_draining(self, nodes: List[Node]) -> List[Node]:
        ret = []
        for node in nodes:
            if not node.hostname:
                logging.info("Node %s has no hostname.", node)
                continue

            if not node.managed:
                logging.debug("Ignoring attempt to drain unmanaged %s", node)
                continue

            ret.append(node)
        return ret

    def handle_post_delete(self, nodes: List[Node]) -> List[Node]:
        ret = []
        for node in nodes:
            if not node.hostname:
                continue
            ret.append(node)
        return ret

    def parse_jobs(
        self,
        force: bool = False,
    ) -> List[Job]:

        if force or self.__jobs_cache is None:
            self.__jobs_cache = parse_jobs(
                self.guacdb
            )

        return self.__jobs_cache

    def _read_jobs_and_nodes(
        self, config: Dict
    ) -> Tuple[List[Job], List[SchedulerNode]]:
        """
        this is cached at the library level
        """
        nodes = self.parse_scheduler_nodes()
        jobs = self.parse_jobs()
        return jobs, nodes

    def parse_scheduler_nodes(
        self,
        force: bool = False,
    ) -> List[Node]:
        if force or self.__scheduler_nodes_cache is None:
            self.__scheduler_nodes_cache = parse_scheduler_nodes(
                self.guacdb
            )
        return self.__scheduler_nodes_cache

    def _validate_reverse_dns(self, node: Node) -> bool:
        # let's make sure the hostname is valid and reverse
        # dns compatible before registering to the scheduler
        try:
            addr_info = socket.gethostbyaddr(node.private_ip)
        except Exception as e:
            logging.error(
                "Could not convert private_ip(%s) to hostname using gethostbyaddr() for %s: %s",
                node.private_ip,
                node,
                str(e),
            )
            return False

        addr_info_ips = addr_info[-1]
        if isinstance(addr_info_ips, str):
            addr_info_ips = [addr_info_ips]

        if node.private_ip not in addr_info_ips:
            logging.warning(
                "%s has a hostname that does not match the"
                + " private_ip (%s) reported by cyclecloud (%s)! Skipping",
                node,
                addr_info_ips,
                node.private_ip,
            )
            return False

        addr_info_hostname = addr_info[0].split(".")[0]
        if addr_info_hostname.lower() != node.hostname.lower():
            logging.warning(
                "%s has a hostname that can not be queried via reverse"
                + " dns (private_ip=%s cyclecloud hostname=%s reverse dns hostname=%s)."
                + " This is common and usually repairs itself. Skipping",
                node,
                node.private_ip,
                node.hostname,
                addr_info_hostname,
            )
            return False
        return True

    def __repr__(self) -> str:
        return "GuacDriver(res_def={})".format(self.resource_definitions)

def parse_jobs(
    guacdb: GuacDatabase
) -> List[Job]:
    """
    Parses Guacamole Connections and creates relevant hpc.autoscale.job.job.Job objects
    """
    ret: List[Job] = []

    response: Dict = guacdb.get_connections()

    for record in response:
        # Skip Completed and Running connections
        if record[GuacConnectionAttributes.Status] == GuacConnectionStates.Completed:
            continue
        if record[GuacConnectionAttributes.Status] == GuacConnectionStates.Running:
            continue
    
        job_id = record["connection_id"]
        node_count = 1
        my_job_id = str(job_id)

        job = Job(
            name=my_job_id,
            node_count=node_count,
            colocated=False,
            constraints={"ncpus":1, "exclusive": True}
        )
        # TOFIX: This can never been executed
        # if record[GuacConnectionAttributes.Status] == GuacConnectionStates.Running:
        #     job.executing_hostnames=record["hostname"]
        job.iterations_remaining = 1
        ret.append(job)

    return ret


def parse_scheduler_nodes(
    guacdb: GuacDatabase
) -> List[Node]:
    """
    Get the list of active connections assigned to nodes
    """
    ret: List[Node] = []
    connections: List[Dict] = guacdb.get_active_connections()

    for connection in connections:

        node = parse_scheduler_node(connection)

        if not node.available.get("ccnodeid"):
            node.metadata["override_resources"] = False
            logging.fine(
                "'ccnodeid' is not defined so %s has not been joined to the cluster by the autoscaler"
                + " yet or this is not a CycleCloud managed node",
                node,
            )
        ret.append(node)
    return ret


def parse_scheduler_node(
    ndict: Dict
) -> SchedulerNode:
    """
    Implementation of parsing a single scheduler node.
    """

    hostname = ndict["hostname"]

    node = SchedulerNode(hostname)
    node.available["ccnodeid"] = ndict["nodeid"]
    # Node is exclusive for the job
    #node.closed = True
    state = ndict[GuacConnectionAttributes.Status] or ""

    node.metadata["guac_state"] = state

    if GuacConnectionStates.Completed in state:
        node.marked_for_deletion = True
        node.__assignments = set()
    else:
        node.assign(str(ndict["connection_id"]))

    # TODO : Add last_state_change_time ?
    # node.metadata["last_state_change_time"] = ndict.get("last_state_change_time", "")

    return node
