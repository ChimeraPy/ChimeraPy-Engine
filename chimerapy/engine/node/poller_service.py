from typing import Optional, Dict, Tuple, List
import threading
import logging

import zmq

from chimerapy.engine import _logger
from ..states import NodeState
from ..networking import Subscriber, DataChunk
from ..data_protocols import NodePubTable, NodePubEntry
from ..service import Service
from ..eventbus import EventBus, Event
from .events import NewInBoundDataEvent


class PollerService(Service):
    def __init__(
        self,
        name: str,
        in_bound: List[str],
        in_bound_by_name: List[str],
        state: NodeState,
        eventbus: EventBus,
        follow: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(name)

        # Parameters
        self.in_bound: List[str] = in_bound
        self.in_bound_by_name: List[str] = in_bound_by_name
        self.follow: Optional[str] = follow
        self.state = state
        self.eventbus = eventbus

        # Logging
        if logger:
            self.logger = logger
        else:
            self.logger = _logger.getLogger("chimerapy-engine")

        # State variables
        self.running: bool = False

        # Containers
        self.p2p_subs: Dict[str, Subscriber] = {}
        self.socket_to_sub_name_mapping: Dict[zmq.Socket, Tuple[str, str]] = {}
        self.sub_poller = zmq.Poller()
        self.poll_inputs_thread: Optional[threading.Thread] = None
        self.in_bound_data: Dict[str, DataChunk] = {}

    ####################################################################
    ## Lifecycle Hooks
    ####################################################################

    async def teardown(self):

        # Turn off
        self.running = False

        # Stop poller
        if self.poll_inputs_thread:
            self.poll_inputs_thread.join()
            # self.logger.debug(f"{self}: polling thread shutdown")

        # Shutting down subscriber
        for sub in self.p2p_subs.values():
            sub.shutdown()
            # self.logger.debug(f"{self}: subscriber shutdown")

        # self.logger.debug(f"{self}: shutdown")

    ####################################################################
    ## Helper Methods
    ####################################################################

    def setup_connections(self, node_pub_table: NodePubTable):

        # We determine all the out bound nodes
        for i, in_bound_id in enumerate(self.in_bound):

            self.logger.debug(
                f"{self}: Setting up clients: {self.state.id}: {node_pub_table}"
            )

            # Determine the host and port information
            in_bound_entry: NodePubEntry = node_pub_table.table[in_bound_id]

            # Create subscribers to other nodes' publishers
            p2p_subscriber = Subscriber(
                host=in_bound_entry.ip, port=in_bound_entry.port
            )

            # Storing all subscribers
            self.p2p_subs[in_bound_id] = p2p_subscriber
            self.socket_to_sub_name_mapping[p2p_subscriber._zmq_socket] = (
                self.in_bound_by_name[i],
                in_bound_id,
            )

        # After creating all subscribers, use a poller to track them all
        for sub in self.p2p_subs.values():
            self.sub_poller.register(sub._zmq_socket, zmq.POLLIN)

        # Then start a thread to read the sub poller
        self.poll_inputs_thread = threading.Thread(target=self.poll_inputs)
        self.poll_inputs_thread.start()

    def poll_inputs(self):

        self.running = True

        while self.running:

            # Wait until we get data from any of the subscribers
            events = dict(self.sub_poller.poll(timeout=1000))

            # self.logger.debug(f"{self}: polling inputs: {events}")

            # Empty if no events
            if len(events) == 0:
                continue

            # self.logger.debug(f"{self}: polling event processing {len(events)}")

            # Default value
            follow_event = False

            # Else, update values
            for s in events:  # socket

                self.logger.debug(f"{self}: processing event {s}")

                # Update
                name, id = self.socket_to_sub_name_mapping[s]  # inbound
                serial_data_chunk = s.recv()
                self.in_bound_data[name] = DataChunk.from_bytes(serial_data_chunk)

                # Update flag if new values are coming from the node that is
                # being followed
                if self.follow == id:
                    follow_event = True

            # If update on the follow and all inputs available, then use the inputs
            if follow_event and len(self.in_bound_data) == len(self.in_bound):
                self.eventbus.send(
                    Event("in_step", NewInBoundDataEvent(self.in_bound_data))
                )
                # self.logger.debug(f"{self}: got inputs")
