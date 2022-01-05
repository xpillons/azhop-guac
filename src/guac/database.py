
from typing import Any, Dict, List, Optional
import mysql.connector
from configparser import ConfigParser

class GuacConnectionStates:
    Queued = "queued"
    Ready = "ready"
    Assigned = "assigned"
    Released = "released"

class GuacConnectionAttributes:
    Status = "status"
    NodeArray = "nodearray"
    NodeId = "nodeid"

class GuacDatabase():
    """
    This class is used to interact with the Guacamole database
    """
    def __init__(
        self,
        config: Dict[str, Any],
    ) -> None:
        self.config = config
        self.connection = None
        self.cursor = None
        self.initialize()

    def initialize(self) -> None:
        parser = ConfigParser()
        # This is a trick to get the config file to be parsed as a section
        with open(self.config["config_file"]) as stream:
            parser.read_string("[guac]\n" + stream.read()) 
        guac_config = parser["guac"]
        self.connection = mysql.connector.connect(
            host=guac_config["mysql-hostname"],
            user=guac_config["mysql-username"],
            password=guac_config["mysql-password"],
            database=guac_config["mysql-database"])

    def get_queued_connections(self) -> Dict:
        """
        Get queued connections
        """
        self.cursor = self.connection.cursor()
        sql = "select connection_id from guacamole_connection_attribute where attribute_name=%s and attribute_value=%s"
        self.cursor.execute(sql, (GuacConnectionAttributes.Status, GuacConnectionStates.Queued))
        return self.cursor.fetchall()

    def get_active_connections(self) -> List[Dict]:
        """
        Get active connections
        """
        return self.get_connections(GuacConnectionStates.Assigned)

    def get_connections(self, state: Optional[GuacConnectionStates] = None) -> List[Dict]:
        """
        Get active connections
        """
        self.cursor = self.connection.cursor()
        sql = "select connection_id from guacamole_connection_attribute where attribute_name=%s"
        if state:
            sql += " and attribute_value=%s"
            self.cursor.execute(sql, (GuacConnectionAttributes.Status, state))
        else:
            self.cursor.execute(sql, (GuacConnectionAttributes.Status,))
        
        records = self.cursor.fetchall()
        ret = []
        for record in records:
            item = {}
            item["connection_id"] = record[0]
            conn = self.get_connection(record[0])
            item["connection_name"] = conn[0][1]
            item.update(self.get_connection_attributes(record[0]))
            ret.append(item)

        return ret

    def get_connection_attributes(self, connection_id: int) -> Dict:
        """
        Get all connections attributes for a connection
        """
        self.cursor = self.connection.cursor()
        sql = "SELECT connection_id, attribute_name, attribute_value FROM guacamole_connection_attribute where connection_id=%s"
        self.cursor.execute(sql, (connection_id,))
        attributes = self.cursor.fetchall()
        ret = {}
        for attribute in attributes:
            ret[attribute[1]] = attribute[2]
        return ret

    def get_connection(self, connection_id: int) -> Dict:
        """
        Get a connection from it's id
        """
        self.cursor = self.connection.cursor()
        sql = "SELECT connection_id, connection_name FROM guacamole_connection where connection_id=%s"
        self.cursor.execute(sql, (connection_id,))
        return self.cursor.fetchall()

    def assign_connection_to_host(self, connection_id: int, hostname: str) -> None:
        """
        Assign a connection to a host
        """
        self.cursor = self.connection.cursor()
        sql = "update guacamole_connection set connection_name=%s where connection_id=%s"
        self.cursor.execute(sql, (hostname, connection_id))
        sql = "update guacamole_connection_parameter set parameter_value=%s where connection_id=%s and parameter_name='hostname'"
        self.cursor.execute(sql, (hostname, connection_id))
        self.connection.commit()

    def update_connection_nodeid(self, connection_id: int, nodeid: str) -> None:
        """
        Update the status of a connection
        """
        self.cursor = self.connection.cursor()
        sql = "update guacamole_connection_attribute set attribute_value=%s where connection_id=%s and attribute_name=%s"
        self.cursor.execute(sql, (nodeid, connection_id, GuacConnectionAttributes.NodeId))
        self.connection.commit()

    def update_connection_status(self, connection_id: int, status: GuacConnectionStates) -> None:
        """
        Update the status of a connection
        """
        self.cursor = self.connection.cursor()
        sql = "update guacamole_connection_attribute set attribute_value=%s where connection_id=%s and attribute_name=%s"
        self.cursor.execute(sql, (status, connection_id, GuacConnectionAttributes.Status))
        self.connection.commit()