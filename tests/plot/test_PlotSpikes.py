import os
import unittest
import tempfile
import numpy as np
import random
from .. import BaseTestCase
from collections import defaultdict
import pyneuroml.plot.PlotSpikes as pyplts
from pyneuroml.lems import load_sim_data_from_lems_file
from pyneuroml.plot import get_spike_data_files_from_lems


class TestPlotSpikes(BaseTestCase):
    """Test suite for the PlotSpikes module."""

    def setUp(self):
        """Set up test data for the test suite."""
        self.spike_data = []

        num_neurons_pop1 = 1000
        num_spikes_pop1 = 5000
        population1_times = [random.uniform(0, 1000) for _ in range(num_spikes_pop1)]
        population1_ids = [
            random.randint(0, num_neurons_pop1 - 1) for _ in range(num_spikes_pop1)
        ]
        self.spike_data.append(
            {"name": "Population1", "times": population1_times, "ids": population1_ids}
        )

        num_neurons_pop2 = 500
        num_spikes_pop2 = 2000
        population2_times = [random.uniform(0, 1000) for _ in range(num_spikes_pop2)]
        population2_ids = [
            random.randint(0, num_neurons_pop2 - 1) for _ in range(num_spikes_pop2)
        ]
        self.spike_data.append(
            {
                "name": "Population2",
                "times": population2_times,
                "ids": [id + num_neurons_pop1 for id in population2_ids],
            }
        )

    def test_plot_spikes_from_data(self):
        """Test the plot_spikes function with spike data."""
        pyplts.plot_spikes(
            spiketime_files=[],
            spike_data=self.spike_data,
            show_plots_already=True,
            save_spike_plot_to="spike-plot-test.png",
        )
        self.assertIsFile("spike-plot-test.png")
        os.unlink("spike-plot-test.png")

    def test_plot_spikes_from_files(self):
        """Test the plot_spikes function with spike time files."""
        spike_file = tempfile.NamedTemporaryFile(mode="w", delete=False, dir=".")

        # Write spike data to the temporary file
        times = defaultdict(list)
        unique_ids = []
        spike_data = []
        for pop_data in self.spike_data:
            for i, (time, id) in enumerate(zip(pop_data["times"], pop_data["ids"])):
                print(f"{id} {time}", file=spike_file)
                if id not in times:
                    times[id] = []
                times[id].append(time)
                unique_ids.append(id)
        max_time = max(max(times[id]) for id in times)
        max_id = max(unique_ids)
        for id in unique_ids:
            spike_data.append(
                {
                    "name": f"Population_{id}",
                    "times": times[id],
                    "ids": [id] * len(times[id]),
                }
            )

        spike_file.flush()
        spike_file.close()

        # Generate a plot from the spike time file and save it to a file
        pyplts.plot_spikes(
            spiketime_files=[spike_file.name],
            spike_data=spike_data,
            show_plots_already=True,
            save_spike_plot_to="spike-plot-from-file-test.png",
        )
        self.assertIsFile("spike-plot-from-file-test.png")

        # Clean up the generated files
        os.unlink("spike-plot-from-file-test.png")
        os.unlink(spike_file.name)

    def test_plot_spikes_from_lems_file(self):
        """Test plot_spikes_from_lems_file function"""
        spike_file = tempfile.NamedTemporaryFile(mode="w", delete=False, dir=".")
        for i in range(0, 1):
            print(f"{i*10} 0", file=spike_file)
            print(f"{i*10+5} 1", file=spike_file)
            print(f"{i*10+10} 2", file=spike_file)

        spike_file.flush()
        spike_file.close()

        spike_file_name = os.path.abspath(spike_file.name)

        lems_contents = """
<Lems>

    <!--

        This LEMS file has been automatically generated using PyNeuroML v1.1.13 (libNeuroML v0.5.8)

     -->

    <!-- Specify which component to run -->
    <Target component="example_izhikevich2007network_sim"/>

    <!-- Include core NeuroML2 ComponentType definitions -->
    <Include file="Cells.xml"/>
    <Include file="Networks.xml"/>
    <Include file="Simulation.xml"/>

    <Include file="izhikevich2007_network.nml"/>

    <Simulation id="example_izhikevich2007network_sim" length="1000ms" step="0.1ms" target="IzNet" seed="123">  <!-- Note seed: ensures same random numbers used every run -->
        <EventOutputFile id="Spikes_file__IzhPop0" fileName="{spike_file_name}" format="ID_TIME">
            <EventSelection id="0" select="IzhPop0[0]" eventPort="spike">
            </EventSelection>
            <EventSelection id="1" select="IzhPop0[1]" eventPort="spike">
            </EventSelection>
            <EventSelection id="2" select="IzhPop0[2]" eventPort="spike">
            </EventSelection>
            <EventSelection id="3" select="IzhPop0[3]" eventPort="spike">
            </EventSelection>
            <EventSelection id="4" select="IzhPop0[4]" eventPort="spike">
            </EventSelection>
            <EventSelection id="5" select="IzhPop0[5]" eventPort="spike">
            </EventSelection>
        </EventOutputFile>
        <EventOutputFile id="Spikes_file__IzhPop1" fileName="{spike_file_name}" format="ID_TIME">
            <EventSelection id="6" select="IzhPop1[0]" eventPort="spike">
            </EventSelection>
            <EventSelection id="7" select="IzhPop1[1]" eventPort="spike">
            </EventSelection>
            <EventSelection id="8" select="IzhPop1[2]" eventPort="spike">
            </EventSelection>
            <EventSelection id="9" select="IzhPop1[3]" eventPort="spike">
            </EventSelection>
            <EventSelection id="10" select="IzhPop1[4]" eventPort="spike">
            </EventSelection>
        </EventOutputFile>



    </Simulation>

</Lems>
    """

        lems_file = tempfile.NamedTemporaryFile(mode="w", delete=False, dir=".")
        print(lems_contents.format(spike_file_name=spike_file_name), file=lems_file)
        lems_file.flush()
        lems_file.close()

        for i in range(6):
            file_name = f"IzhPop0[{i}].dat"
            with open(file_name, "w") as f:
                for j in range(100):
                    print(f"{j*10} {i}", file=f)

        for i in range(5):
            file_name = f"IzhPop1[{i}].dat"
            with open(file_name, "w") as f:
                for j in range(100):
                    print(f"{j*10} {i+6}", file=f)

        pyplts.plot_spikes_from_lems_file(
            lems_file_name=lems_file.name,
            base_dir=".",
            show_plots_already=True,
            save_spike_plot_to="spikes-test-from-lems-file.png",
            rates=False,
            rate_window=50,
            rate_bins=500,
        )
        self.assertIsFile("spikes-test-from-lems-file.png")

        pyplts.plot_spikes_from_lems_file(
            lems_file_name=lems_file.name,
            base_dir=".",
            show_plots_already=False,
            save_spike_plot_to="spikes-test-from-lems-file-2.png",
            rates=True,
            rate_window=50,
            rate_bins=500,
        )
        self.assertIsFile("spikes-test-from-lems-file-2.png")

        os.unlink("spikes-test-from-lems-file.png")
        os.unlink("spikes-test-from-lems-file-2.png")
        os.unlink(spike_file_name)
        os.unlink(lems_file.name)

        for i in range(6):
            file_name = f"IzhPop0[{i}].dat"
            os.unlink(file_name)
        for i in range(5):
            file_name = f"IzhPop1[{i}].dat"
            os.unlink(file_name)

    @unittest.skip("Skipping until write_spike_data_to_hdf5 is implemented")
    def test_plot_spikes_from_sonata_file(self):
        """Test the plot_spikes function with a SONATA-format HDF5 file."""
        spike_data = [
            {
                "name": "Population1",
                "times": np.array([1.0, 2.0, 3.0]),
                "ids": np.array([1, 2, 3]),
            },
            {
                "name": "Population2",
                "times": np.array([2.5, 3.5]),
                "ids": np.array([4, 5]),
            },
        ]

        # Create a temporary HDF5 file
        hdf5_file = tempfile.NamedTemporaryFile(delete=False, dir=".", suffix=".h5")
        hdf5_file.close()

        # write_spike_data_to_hdf5(hdf5_file.name, spike_data)

        # Generate a plot from the SONATA HDF5 file and save it to a file
        pyplts.plot_spikes(
            spiketime_files=[hdf5_file.name],
            format="sonata",
            show_plots_already=False,
            save_figure_to="spike-plot-from-sonata-test.png",
        )
        self.assertIsFile("spike-plot-from-sonata-test.png")

        # Clean up the generated files
        os.unlink("spike-plot-from-sonata-test.png")
        os.unlink(hdf5_file.name)


if __name__ == "__main__":
    unittest.main()
