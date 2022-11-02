from typing import Dict, List, Any, Optional
import multiprocessing as mp
from multiprocessing.process import AuthenticationString
import time
import socket
import logging
import queue

mp.set_start_method("fork")

logger = logging.getLogger("chimerapy")

from .client import Client
from .server import Server
from .data_handlers import OutputsHandler
from . import enums
from .utils import log, clear_queue


class Node(mp.Process):
    def __init__(self, name: str):
        super().__init__(daemon=True)

        # Saving input parameters
        self.name = name
        self.status = {"INIT": 0, "CONNECTED": 0, "READY": 0}

    def __repr__(self):
        return f"<Node {self.name}>"

    def __str__(self):
        return self.__repr__()

    def __getstate__(self):
        """called when pickling - this hack allows subprocesses to
        be spawned without the AuthenticationString raising an error"""
        state = self.__dict__.copy()
        conf = state["_config"]
        if "authkey" in conf:
            # del conf['authkey']
            conf["authkey"] = bytes(conf["authkey"])
        return state

    def __setstate__(self, state):
        """for unpickling"""
        state["_config"]["authkey"] = AuthenticationString(state["_config"]["authkey"])
        self.__dict__.update(state)

    def config(
        self,
        host: str,
        port: int,
        in_bound: List[str],
        out_bound: List[str],
        networking: bool = True,
    ):

        # Obtaining worker information
        self.worker_host = host
        self.worker_port = port

        # Storing p2p information
        self.p2p_info = {"in_bound": in_bound, "out_bound": out_bound}

        # Keeping track of the node's state
        self.running = mp.Value("i", True)

        # Saving other parameters
        self.networking = networking

        # Creating initial values
        self.latest_value = None

        logger.debug(f"{self}: finished config")

    @log
    def _prep(self):

        # Create container for p2p clients
        self.p2p_clients = {}

        # Create input and output queue
        self.in_queue = queue.Queue()
        self.out_queue = queue.Queue()

        # Create the queues for each in-bound connection
        self.in_bound_queues = {x: queue.Queue() for x in self.p2p_info["in_bound"]}
        self.in_bound_data = {x: None for x in self.p2p_info["in_bound"]}
        self.all_inputs_ready = False
        self.new_data_available = False

        # Create the threads that manager the incoming and outgoing
        # data chunks
        self.outputs_handler = OutputsHandler(
            self.name, self.out_queue, self.p2p_info["out_bound"], self.p2p_clients
        )
        self.outputs_handler.start()

        # Defining protocol responses
        self.to_worker_handlers = {
            enums.SHUTDOWN: self.shutdown,
            enums.WORKER_BROADCAST_NODE_SERVER_DATA: self.process_node_server_data,
            enums.WORKER_REQUEST_STEP: self.forward,
            enums.WORKER_REQUEST_GATHER: self.provide_gather,
            enums.WORKER_START_NODES: self.start_node,
            enums.WORKER_STOP_NODES: self.stop_node,
        }
        self.from_node_handlers = {
            enums.NODE_DATA_TRANSFER: self.received_data,
        }
        self.to_node_handlers = {}

        # Keeping parameters
        self.step_id = 0
        self.worker_signal_start = 0
        self.status["INIT"] = 1

        if self.networking:

            # Create client to the Worker
            self.client = Client(
                host=self.worker_host,
                port=self.worker_port,
                name=f"Node {self.name}",
                connect_timeout=5.0,
                sender_msg_type=enums.NODE_MESSAGE,
                accepted_msg_type=enums.WORKER_MESSAGE,
                handlers=self.to_worker_handlers,
            )
            logger.debug(f"{self}: Node creating Client to connect to Worker")

            self.client.start()
            logger.debug(f"{self}: connected to Worker")

            # Create server
            self.server = Server(
                port=5000,
                name=f"Node {self.name}",
                max_num_of_clients=len(self.p2p_info["out_bound"]),
                sender_msg_type=enums.NODE_MESSAGE,
                accepted_msg_type=enums.NODE_MESSAGE,
                handlers=self.from_node_handlers,
            )
            self.server.start()

            # Inform client that Node is INITIALIZED!
            self.client.send(
                {
                    "signal": enums.NODE_STATUS,
                    "data": {
                        "node_name": self.name,
                        "status": self.status,
                        "host": self.server.host,
                        "port": self.server.port,
                    },
                }
            )

    def process_node_server_data(self, msg: Dict):

        # We determine all the out bound nodes
        for out_bound_name in self.p2p_info["out_bound"]:

            logger.debug(f"{self}: Setting up clients: {self.name}: {msg}")

            # Determine the host and port information
            out_bound_info = msg["data"][out_bound_name]

            # Create a client to the out bound node
            p2p_client = Client(
                host=out_bound_info["host"],
                port=out_bound_info["port"],
                name=self.name,
                connect_timeout=5.0,
                sender_msg_type=enums.NODE_MESSAGE,
                accepted_msg_type=enums.NODE_MESSAGE,
                handlers=self.to_node_handlers,
            )

            # # Save the client
            self.p2p_clients[out_bound_name] = p2p_client

        # Notify to the worker that the node is fully CONNECTED
        self.status["CONNECTED"] = 1
        self.client.send(
            {
                "signal": enums.NODE_STATUS,
                "data": {
                    "node_name": self.name,
                    "status": self.status,
                },
            }
        )

    def received_data(self, msg: Dict, client_socket: socket.socket):

        # Mark that new data was received
        self.new_data_available = True

        # Extract the data from the pickle
        coupled_data: Dict = msg["data"]["outputs"]

        # Sort the given data into their corresponding queue
        self.in_bound_data[msg["data"]["sent_from"]] = coupled_data["data"]

        if not all([type(x) != type(None) for x in self.in_bound_data.values()]):
            return None
        else:
            self.all_inputs_ready = True

    def provide_gather(self, msg: Dict):

        self.client.send(
            {
                "signal": enums.NODE_REPORT_GATHER,
                "data": {"node_name": self.name, "latest_value": self.latest_value},
            }
        )

    def prep(self):
        """User-define method"""
        ...

    def ready(self):

        # Notify to the worker that the node is fully READY
        self.status["READY"] = 1
        if self.networking:
            self.client.send(
                {
                    "signal": enums.NODE_STATUS,
                    "data": {
                        "node_name": self.name,
                        "status": self.status,
                    },
                }
            )

    def waiting(self):

        # Only wait if connected to Worker
        if self.networking:

            # Wait until worker says to start
            while self.running.value:
                if self.worker_signal_start:
                    break
                else:
                    time.sleep(0.1)

    def start_node(self, msg: Dict):
        self.worker_signal_start = True
        logger.debug(f"{self}: start")

    def stop_node(self, msg: Dict):
        self.running.value = False

    def forward(self, msg: Dict):

        # If no in_bound, just send data
        if len(self.p2p_info["in_bound"]) == 0:
            output = self.step()

        else:

            # Else, we have to wait for inputs
            while True:

                if self.all_inputs_ready and self.new_data_available:
                    inputs = self.in_bound_data.copy()
                    self.new_data_available = False
                else:
                    time.sleep(1 / 100)  # Required to allow threads to execute
                    continue

                logger.debug(f"{self}: got inputs")

                # Once we get them, pass them through!
                output = self.step(inputs)
                break

        # If output generated, send it!
        if type(output) != type(None):

            # Send out the output to the OutputsHandler
            logger.debug(f"{self}: placed data to out_queue")
            self.out_queue.put({"step_id": self.step_id, "data": output})

            # And then save the latest value
            self.latest_value = output

        # Update the counter
        self.step_id += 1

    def step(self, data_dict: Optional[Dict[str, Any]] = None):
        """User-define method"""
        ...

    def main(self):
        """User-possible overwritten method"""

        while self.running.value:
            self.forward({})

    def teardown(self):
        """User-define method"""
        ...

    def _teardown(self):

        # Clear out the queues
        clear_queue(self.in_queue)
        clear_queue(self.out_queue)

        # Shutdown the inputs and outputs threads
        self.outputs_handler.shutdown()

        # Shutting down networking
        if self.networking:
            # Shutdown the client
            self.client.shutdown()

            # Shutdown the server
            self.server.shutdown()

    def run(self):

        logger.debug(f"{self}: initialized")

        # Performing preparation for the while loop
        self._prep()
        self.prep()

        assert isinstance(self.in_queue, queue.Queue)

        logger.debug(f"{self}: finished prep")

        # Signal that Node is ready
        self.ready()

        logger.debug(f"{self}: is ready")

        # Now waiting for the Worker to inform the node to execute
        self.waiting()

        logger.debug(f"{self}: is running")

        self.main()

        logger.debug(f"{self}: is exiting")

        self.teardown()
        self._teardown()

        logger.debug(f"{self}: finished teardown")

    def shutdown(self, msg: Dict = {}):

        self.running.value = False
