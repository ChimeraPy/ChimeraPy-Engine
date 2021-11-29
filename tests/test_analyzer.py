import unittest
import pathlib

import pandas as pd

import pymmdt as mm
import pymmdt.video
import pymmdt.tabular

TEST_DIR = pathlib.Path.cwd() / 'tests'
DATA_DIR = TEST_DIR  / 'data'
TEST_OUTPUT = TEST_DIR / 'test_output'

class TestAnalyzer(unittest.TestCase):
    
    def setUp(self):

        # Load data 
        a1_data = pd.read_csv(DATA_DIR / 'test.csv')

        # Converting the UNIX timestamps to pd.DatetimeIndex to improve consistency and reability
        a1_data['time'] = pd.to_timedelta(a1_data['time'], unit='s')

        # Get start time
        start_time = a1_data['time'][0]
     
        # Construct data streams
        ds1 = pymmdt.tabular.TabularDataStream(
            name='csv',
            data=a1_data,
            time_column='time',
            data_columns=['data']
        )
        ds2 = pymmdt.video.VideoDataStream(
            name='video', 
            video_path=DATA_DIR / 'test_video1.mp4', 
            start_time=start_time
        )

        # Create processes
        show_video = pymmdt.video.ShowVideo(
            inputs=['draw_video'],
            ms_delay=10
        )

        # Initiate collector and analyzer
        self.processes = [show_video]
        self.collector = mm.Collector([ds1, ds2])
        self.session = mm.Session()
        self.analyzer = mm.Analyzer(
            self.collector, 
            self.processes,
            self.session
        )

    # def test_process_graph(self):
        
    #     path = TEST_OUTPUT / 'nx_test.png'
        
    #     # nx.nx_agraph.write_dot(self.analyzer.data_flow_graph, path)
    #     p=nx.drawing.nx_pydot.to_pydot(self.analyzer.data_flow_graph)
    #     p.write_png(path)

    def test_getting_pipeline(self):
    
        # Get the first sample
        sample = self.collector[0]

        # Obtain the data pipeline
        data_pipeline = self.analyzer.get_sample_pipeline(sample)

    def tearDown(self):
        ...

if __name__ == "__main__":
    unittest.main()
