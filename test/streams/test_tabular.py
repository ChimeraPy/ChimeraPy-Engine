# Built-in Imports
import os
import pathlib
import logging
import uuid
import time

# Third-party
import pandas as pd
import numpy as np
import pytest
import chimerapy as cp

logger = logging.getLogger("chimerapy")

# Constants
CWD = pathlib.Path(os.path.abspath(__file__)).parent.parent
TEST_DATA_DIR = CWD / "data"


class TabularNode(cp.Node):
    def step(self):

        time.sleep(1 / 10)

        # Testing different types
        data = {"time": time.time(), "content": "HELLO"}
        self.save_tabular(name="test", data=data)

        data = pd.Series({"time": time.time(), "content": "GOODBYE"})
        self.save_tabular(name="test", data=data)

        data = pd.DataFrame({"time": [time.time()], "content": ["WAIT!"]})
        self.save_tabular(name="test", data=data)


@pytest.fixture
def tabular_node():

    # Create a node
    an = TabularNode(name="tn")
    an.config("", 9000, TEST_DATA_DIR, [], [], follow=None, networking=False)
    an._prep()

    return an


def test_tabular_record():

    # Check that the tabular was created
    expected_tabular_path = TEST_DATA_DIR / "test.csv"
    try:
        os.remove(expected_tabular_path)
    except FileNotFoundError:
        ...

    # Create the record
    tr = cp.records.TabularRecord(dir=TEST_DATA_DIR, name="test")

    # Write to tabular file
    for i in range(5):
        data = {"time": time.time(), "content": "HELLO"}
        tabular_chunk = {
            "uuid": uuid.uuid4(),
            "name": "test",
            "data": data,
            "dtype": "tabular",
        }
        tr.write(tabular_chunk)

    assert expected_tabular_path.exists()


def test_save_handler_tabular(save_handler_and_queue):

    # Check that the tabular was created
    expected_tabular_path = TEST_DATA_DIR / "test.csv"
    try:
        os.remove(expected_tabular_path)
    except FileNotFoundError:
        ...

    # Decoupling
    save_handler, save_queue = save_handler_and_queue

    # Write to tabular file
    for i in range(5):
        data = {"time": time.time(), "content": "HELLO"}
        tabular_chunk = {
            "uuid": uuid.uuid4(),
            "name": "test",
            "data": data,
            "dtype": "tabular",
        }
        save_queue.put(tabular_chunk)

    # Shutdown save handler
    save_handler.shutdown()
    save_handler.join()

    # Check that the tabular was created
    expected_tabular_path = save_handler.logdir / "test.csv"
    assert expected_tabular_path.exists()


def test_node_save_tabular_single_step(tabular_node):

    # Check that the tabular was created
    expected_tabular_path = tabular_node.logdir / "test.csv"
    try:
        os.remove(expected_tabular_path)
    except FileNotFoundError:
        ...

    # Write to tabular file
    for i in range(5):
        tabular_node.step()

    # Stop the node the ensure tabular completion
    tabular_node.shutdown()
    tabular_node._teardown()
    time.sleep(1)

    # Check that the tabular was created
    assert expected_tabular_path.exists()


def test_node_save_tabular_stream(tabular_node):

    # Check that the tabular was created
    expected_tabular_path = tabular_node.logdir / "test.csv"
    try:
        os.remove(expected_tabular_path)
    except FileNotFoundError:
        ...

    # Stream
    tabular_node.start()

    # Wait to generate files
    time.sleep(10)

    tabular_node.shutdown()
    tabular_node._teardown()
    tabular_node.join()

    # Check that the tabular was created
    assert expected_tabular_path.exists()
