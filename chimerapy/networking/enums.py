from enum import Enum


class GENERAL_MESSAGE(Enum):
    SHUTDOWN = -1
    OK = 0
    FILE_TRANSFER_START = 1
    FILE_TRANSFER_END = 2


class CLIENT_MESSAGE(Enum):
    REGISTER = 3


class MANAGER_MESSAGE(Enum):
    CREATE_NODE = 4
    REQUEST_NODE_SERVER_DATA = 5
    BROADCAST_NODE_SERVER_DATA = 6
    REPORT_STATUS = 7
    REQUEST_STEP = 8
    START_NODES = 9
    STOP_NODES = 10
    REQUEST_GATHER = 11
    REQUEST_COLLECT = 12
    REQUEST_CODE_LOAD = 13


class WORKER_MESSAGE(Enum):
    REGISTER = 13
    DEREGISTER = 14
    REPORT_NODE_SERVER_DATA = 15
    BROADCAST_NODE_SERVER_DATA = 16
    REPORT_NODES_STATUS = 17
    COMPLETE_BROADCAST = 18
    REQUEST_STEP = 19
    REQUEST_GATHER = 20
    REPORT_GATHER = 21
    START_NODES = 22
    STOP_NODES = 23
    TRANSFER_COMPLETE = 24


class NODE_MESSAGE(Enum):
    STATUS = 25
    REPORT_GATHER = 26
