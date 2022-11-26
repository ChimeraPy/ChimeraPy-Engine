# Built-in Imports
import time
import logging
import collections

# Third-party Imports
import dill
import pytest
from pytest_lazyfixture import lazy_fixture

# Internal Imports
import chimerapy as cp

logger = logging.getLogger("chimerapy")
from .data_nodes import VideoNode, AudioNode, ImageNode, TabularNode
from ..conftest import linux_run_only, linux_expected_only
from ..mock import DockeredWorker

# References:
# https://www.thepythoncode.com/article/send-receive-files-using-sockets-python

NAME_CLASS_MAP = {
    "vn": VideoNode,
    "img_n": ImageNode,
    "tn": TabularNode,
    "an": AudioNode,
}
NUM_OF_WORKERS = 5


@pytest.fixture
def single_worker_manager(manager, worker):

    # Define graph
    graph = cp.Graph()
    for node_name, node_class in NAME_CLASS_MAP.items():
        graph.add_node(node_class(name=node_name))

    # Connect to the manager
    worker.connect(host=manager.host, port=manager.port)

    # Then register graph to Manager
    manager.register_graph(graph)

    # Specify what nodes to what worker
    manager.map_graph(
        {
            worker.name: list(NAME_CLASS_MAP.keys()),
        }
    )

    return manager


@pytest.fixture
def multiple_worker_manager(manager, worker):

    # Construct graph
    graph = cp.Graph()

    workers = []
    worker_node_map = collections.defaultdict(list)
    for i in range(NUM_OF_WORKERS):
        worker = cp.Worker(name=f"W{i}")
        worker.connect(host=manager.host, port=manager.port)
        workers.append(worker)

        # For each worker, add all possible nodes
        for node_name, node_class in NAME_CLASS_MAP.items():
            node_worker_name = f"W{i}-{node_name}"
            worker_node_map[f"W{i}"].append(node_worker_name)
            graph.add_node(node_class(name=node_worker_name))

    # Then register graph to Manager
    manager.register_graph(graph)

    # Specify what nodes to what worker
    manager.map_graph(worker_node_map)

    yield manager

    for worker in workers:
        worker.shutdown()


@pytest.fixture
def dockered_single_worker_manager(manager, docker_client):

    worker = DockeredWorker(docker_client, name="local")

    # Define graph
    graph = cp.Graph()
    for node_name, node_class in NAME_CLASS_MAP.items():
        graph.add_node(node_class(name=node_name))

    # Connect to the manager
    worker.connect(host=manager.host, port=manager.port)

    # Then register graph to Manager
    manager.register_graph(graph)

    # Specify what nodes to what worker
    manager.map_graph(
        {
            worker.name: list(NAME_CLASS_MAP.keys()),
        }
    )

    return manager


def test_worker_data_archiving(worker):

    # Just for debugging
    # worker.delete_temp = False

    nodes = []
    for node_name, node_class in NAME_CLASS_MAP.items():
        nodes.append(node_class(name=node_name))

    # Simple single node without connection
    for node in nodes:
        msg = {
            "data": {
                "node_name": node.name,
                "pickled": dill.dumps(node),
                "in_bound": [],
                "out_bound": [],
                "follow": None,
            }
        }
        worker.create_node(msg)

    logger.debug("Waiting!")
    time.sleep(2)

    logger.debug("Start nodes!")
    worker.start_nodes({})

    logger.debug("Let nodes run for some time")
    time.sleep(1)

    for node_name in NAME_CLASS_MAP:
        assert (worker.tempfolder / node_name).exists()


@pytest.mark.parametrize(
    "config_manager, expected_number_of_folders",
    [
        (lazy_fixture("single_worker_manager"), 1),
        (lazy_fixture("multiple_worker_manager"), NUM_OF_WORKERS),
        pytest.param(
            lazy_fixture("dockered_single_worker_manager"),
            1,
            marks=linux_run_only,
        ),
    ],
)
def test_manager_worker_data_transfer(config_manager, expected_number_of_folders):

    # Commiting the graph by sending it to the workers
    config_manager.commit_graph()
    config_manager.wait_until_all_nodes_ready(timeout=10)

    # Take a single step and see if the system crashes and burns
    config_manager.start()
    time.sleep(2)
    config_manager.stop()

    # Transfer the files to the Manager's logs
    config_manager.collect()

    # Assert the behavior
    assert len(list(config_manager.logdir.iterdir())) == expected_number_of_folders
