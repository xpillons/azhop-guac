
from typing import Any, Dict, List, Optional
import mariadb
from configparser import ConfigParser
import hpc.autoscale.hpclogging as logging
class GuacConnectionStates:
    Queued = "queued"
    Running = "running"
    Completed = "completed"
    Failed = "failed"

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

    def __del__ (
        self
    ) -> None:
        if self.cursor:
            self.cursor.close()

    def initialize(self) -> None:
        parser = ConfigParser()
        # This is a trick to get the config file to be parsed as a section
        with open(self.config["config_file"]) as stream:
            parser.read_string("[guac]\n" + stream.read()) 
        guac_config = parser["guac"]
        self.connection = mariadb.connect(
            host=guac_config["mysql-hostname"],
            user=guac_config["mysql-username"],
            password=guac_config["mysql-password"],
            database=guac_config["mysql-database"],
            ssl_ca=guac_config["mysql-ssl_ca"])

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
        return self.get_connections(GuacConnectionStates.Running)

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
            item.update(self.get_connection_parameters(record[0]))
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

    def get_connection_parameters(self, connection_id: int) -> Dict:
        """
        Get filetered connections parameters for a connection
        """
        self.cursor = self.connection.cursor()
        sql = "SELECT connection_id, parameter_name, parameter_value FROM guacamole_connection_parameter where connection_id=%s and parameter_name != 'password'"
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

    def get_connection_by_name(self, connection_name: str) -> Dict:
        """
        Get a connection from it's name
        """
        self.cursor = self.connection.cursor()
        sql = "SELECT connection_id, connection_name FROM guacamole_connection where connection_name=%s"
        self.cursor.execute(sql, (connection_name,))
        return self.cursor.fetchall()

    def assign_connection_to_host(self, connection_id: int, hostname: str) -> None:
        """
        Assign a connection to a host
        """
        self.cursor = self.connection.cursor()
        # sql = "update guacamole_connection set connection_name=%s where connection_id=%s"
        # self.cursor.execute(sql, (hostname, connection_id))
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

    def create_new_connection(self, connection_name: str, username: str, password: str, domain: str, nodearray: str) -> int:
        """
        Create a new connection
        """
        ret = -1
        try:
            with self.connection.cursor() as self.cursor:
                sql = "insert into guacamole_connection (connection_name, protocol, max_connections, max_connections_per_user) values (%s, 'rdp', 1, 1)"
                self.cursor.execute(sql, (connection_name,))
                connection_id = self.cursor.lastrowid

                sql = "insert into guacamole_connection_parameter (connection_id, parameter_name, parameter_value) values (%s, %s, %s)"
                values = [  (connection_id,"port","3389"),
                            (connection_id,"hostname",connection_name),
                            (connection_id,"username",username),
                            (connection_id,"password",password),
                            (connection_id,"domain",domain),
                            (connection_id,"ignore-cert","true")
                        ]
                self.cursor.executemany(sql,values)

                sql = "insert into guacamole_connection_attribute (connection_id, attribute_name, attribute_value) values (%s, %s, %s)"
                values = [  (connection_id, "nodearray", nodearray),
                            (connection_id, "status", GuacConnectionStates.Queued),
                            (connection_id, "nodeid", "0")
                ]
                self.cursor.executemany(sql,values)

                sql = "select entity_id from guacamole_entity where type = 'USER' and name=%s"
                self.cursor.execute(sql, (username,))
                records = self.cursor.fetchall()
                if len(records) == 0:
                    sql = "insert into guacamole_entity (type, name) values ('USER', %s)"
                    self.cursor.execute(sql, (username,))
                    entity_id = self.cursor.lastrowid
                    # Adding this record to maintain the entity integrity and because the quacamole site try to insert a full entity record for a user
                    sql = "insert into guacamole_user (entity_id, password_hash, password_salt, password_date) values (%s, 'foo', 'foo', now())"
                    self.cursor.execute(sql, (entity_id,))
                else:
                    entity_id = records[0][0]

                sql = "insert into guacamole_connection_permission (connection_id, entity_id, permission) values (%s, %s, 'READ')"
                self.cursor.execute(sql, (connection_id, entity_id))
                self.connection.commit()
                ret = connection_id
        except Exception as e:
            self.connection.rollback()
            logging.warning("create new connection failed : %s", e)
            logging.exception(str(e))
        return ret

    def delete_connection(self, connection_id: str, username: str) -> None:
        """
        Delete a connection
        """
        try:
            with self.connection.cursor() as self.cursor:

                sql = "select entity_id from guacamole_entity where type = 'USER' and name=%s"
                self.cursor.execute(sql, (username,))
                records = self.cursor.fetchall()
                entity_id = str(records[0][0])

                sql = "delete from guacamole_connection_permission where entity_id=%s and connection_id=%s"
                self.cursor.execute(sql, (entity_id, connection_id,))

                sql = "delete from guacamole_connection_parameter where connection_id=%s"
                self.cursor.execute(sql, (connection_id,))

                sql = "delete from guacamole_connection_attribute where connection_id=%s"
                self.cursor.execute(sql, (connection_id,))

                sql = "delete from guacamole_connection where connection_id=%s"
                self.cursor.execute(sql, (connection_id,))

                self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logging.warning("delete connection failed : %s", e)
            logging.exception(str(e))