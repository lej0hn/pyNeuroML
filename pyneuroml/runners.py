#!/usr/bin/env python3
"""
Util methods related to running models.

File: pyneuroml/utils/runners.py

Copyright 2024 NeuroML contributors
"""


import inspect
import logging
import math
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time
import traceback
import typing
from datetime import datetime
from pathlib import Path
from typing import Optional

import ppft as pp
from lxml import etree

import pyneuroml.utils
import pyneuroml.utils.misc
from pyneuroml import DEFAULTS, __version__
from pyneuroml.errors import UNKNOWN_ERR

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def run_lems_with_jneuroml(
    lems_file_name: str,
    paths_to_include: list = [],
    max_memory: str = DEFAULTS["default_java_max_memory"],
    skip_run: bool = False,
    nogui: bool = False,
    load_saved_data: bool = False,
    reload_events: bool = False,
    plot: bool = False,
    show_plot_already: bool = True,
    exec_in_dir: str = ".",
    verbose: bool = DEFAULTS["v"],
    exit_on_fail: bool = True,
    cleanup: bool = False,
) -> typing.Union[bool, typing.Union[dict, typing.Tuple[dict, dict]]]:
    """Parse/Run a LEMS file with jnml.

    Tip: set `skip_run=True` to only parse the LEMS file but not run the simulation.

    :param lems_file_name: name of LEMS file to run
    :type lems_file_name: str
    :param paths_to_include: additional directory paths to include (for other NML/LEMS files, for example)
    :type paths_to_include: list(str)
    :param max_memory: maximum memory allowed for use by the JVM
    :type max_memory: bool
    :param skip_run: toggle whether run should be skipped, if skipped, file will only be parsed
    :type skip_run: bool
    :param nogui: toggle whether jnml GUI should be shown
    :type nogui: bool
    :param load_saved_data: toggle whether any saved data should be loaded
    :type load_saved_data: bool
    :param reload_events: toggle whether events should be reloaded
    :type reload_events: bool
    :param plot: toggle whether specified plots should be plotted
    :type plot: bool
    :param show_plot_already: toggle whether prepared plots should be shown
    :type show_plot_already: bool
    :param exec_in_dir: working directory to execute LEMS simulation in
    :type exec_in_dir: str
    :param verbose: toggle whether jnml should print verbose information
    :type verbose: bool
    :param exit_on_fail: toggle whether command should exit if jnml fails
    :type exit_on_fail: bool
    :param cleanup: toggle whether the directory should be cleaned of generated files after run completion
    :type cleanup: bool
    """
    logger.info(
        "Loading LEMS file: {} and running with jNeuroML".format(lems_file_name)
    )
    post_args = ""
    post_args += _gui_string(nogui)
    post_args += _include_string(paths_to_include)

    t_run = datetime.now()

    if not skip_run:
        success = run_jneuroml(
            "",
            lems_file_name,
            post_args,
            max_memory=max_memory,
            exec_in_dir=exec_in_dir,
            verbose=verbose,
            report_jnml_output=verbose,
            exit_on_fail=exit_on_fail,
        )

    if not success:
        return False

    if load_saved_data:
        return reload_saved_data(
            lems_file_name,
            base_dir=exec_in_dir,
            t_run=t_run,
            plot=plot,
            show_plot_already=show_plot_already,
            simulator="jNeuroML",
            reload_events=reload_events,
            remove_dat_files_after_load=cleanup,
        )
    else:
        return True


def run_multiple_lems_with(
    num_parallel: typing.Optional[int], sims_spec: typing.Dict[typing.Any, typing.Any]
):
    """Run multiple LEMS simulation files in a pool.

    Uses the `ppft <https://ppft.readthedocs.io/en/latest/>`__ module.

    :param num_parallel: number of simulations to run in parallel, if None, ppft
        will auto-detect
    :type num_parallel: None or int
    :param sims_spec: dictionary with simulation specifications
        Each key of the dict should be the name of the LEMS file to be
        simulated, and the keys will be dictionaries that contain the arguments
        and key word arguments to pass to the `run_lems_with` method:

        .. code-block:: python

            {
                "LEMS1.xml": {
                        "engine": "name of engine",
                        "args": ("arg1", "arg2"),
                        "kwargs": {
                            "kwarg1": value
                        }
            }

        Note that since the name of the simulation file and the engine are
        already explicitly provided, these should not be included again in the
        args/kwargs

    :type sims_spec: dict
    :returns: dict with results of runs, depending on given arguments:

        .. code-block:: python

        {
            "LEMS1.xml": <results>
        }

    :rtype: dict
    """
    results = {}
    if num_parallel is None:
        jobserver = pp.Server()
        logger.info("Created job server by auto-detecting number of jobs")
    else:
        logger.info(f"Created job server using {num_parallel} jobs")
        jobserver = pp.Server(num_parallel)

    function_tuple = inspect.getmembers(sys.modules[__name__], inspect.isfunction)
    ctr = 0
    for sim, sim_dict in sims_spec.items():
        # ppft's submit function only takes args, not kwargs, so we need to
        # create args from provided kwargs
        # In doing so, we end up re-implementing some functionality of the
        # `run_lems_with` function, but that cannot be helped
        found = False
        for fname, function in function_tuple:
            if fname.startswith("run_lems_with") and fname.endswith(sim_dict["engine"]):
                callfunc = inspect.signature(function)
                found = True

                bound_arguments = callfunc.bind(sim_dict["args"], **sim_dict["kwargs"])
                bound_arguments.apply_defaults()
                bound_arguments.arguments["lems_file_name"] = sim

                print(f"[{ctr}/{len(sims_spec)}] Submitting {sim} to jobserver")
                logger.debug(
                    f"[{ctr}/{len(sims_spec)}] Submitting {sim} to jobserver with specs: {bound_arguments.arguments}"
                )
                logger.debug(f"globals are: {globals()}")
                results[sim] = jobserver.submit(
                    function, args=bound_arguments.args, modules=(), globals=globals()
                )
                jobserver.print_stats()
                ctr += 1
                break

        if found is False:
            logger.error(f"No function run_lems_with_{sims_spec['engine']} found")
            return {}

    logger.info("Waiting for jobs to finish")
    jobserver.wait()
    jobserver.print_stats()

    return results


def run_lems_with(engine: str, *args: typing.Any, **kwargs: typing.Any):
    """Run LEMS with specified engine.

    Wrapper around the many `run_lems_with_*` methods.
    The engine should be the suffix, for example, to use
    `run_lems_with_jneuroml_neuron`, engine will be `jneuroml_neuron`.

    All kwargs are passed as is to the function. Please see the individual
    function documentations for information on arguments.

    :param engine: engine to run with
    :type engine: string (valid names are methods)
    :param args: postional arguments to pass to run function
    :param kwargs: named arguments to pass to run function
    :returns: return value of called method

    """
    function_tuple = inspect.getmembers(sys.modules[__name__], inspect.isfunction)
    found = False
    for fname, function in function_tuple:
        if fname.startswith("run_lems_with") and fname.endswith(engine):
            print(f"Running with {fname}")
            found = True
            retval = function(*args, **kwargs)

    if found is False:
        logger.error(f"Could not find engine {engine}. Exiting.")
        return False

    return retval


def run_lems_with_jneuroml_neuron(
    lems_file_name: str,
    paths_to_include: typing.List[str] = [],
    max_memory: str = DEFAULTS["default_java_max_memory"],
    skip_run: bool = False,
    nogui: bool = False,
    load_saved_data: bool = False,
    reload_events: bool = False,
    plot: bool = False,
    show_plot_already: bool = True,
    exec_in_dir: str = ".",
    only_generate_scripts: bool = False,
    compile_mods: bool = True,
    verbose: bool = DEFAULTS["v"],
    exit_on_fail: bool = True,
    cleanup: bool = False,
    realtime_output: bool = False,
) -> typing.Union[bool, typing.Union[dict, typing.Tuple[dict, dict]]]:
    # jnml_runs_neuron=True):  #jnml_runs_neuron=False is Work in progress!!!
    """Run LEMS file with the NEURON simulator

    Tip: set `skip_run=True` to only parse the LEMS file but not run the simulation.

    :param lems_file_name: name of LEMS file to run
    :type lems_file_name: str
    :param paths_to_include: additional directory paths to include (for other NML/LEMS files, for example)
    :type paths_to_include: list(str)
    :param max_memory: maximum memory allowed for use by the JVM
    :type max_memory: bool
    :param skip_run: toggle whether run should be skipped, if skipped, file will only be parsed
    :type skip_run: bool
    :param nogui: toggle whether jnml GUI should be shown
    :type nogui: bool
    :param load_saved_data: toggle whether any saved data should be loaded
    :type load_saved_data: bool
    :param reload_events: toggle whether events should be reloaded
    :type reload_events: bool
    :param plot: toggle whether specified plots should be plotted
    :type plot: bool
    :param show_plot_already: toggle whether prepared plots should be shown
    :type show_plot_already: bool
    :param exec_in_dir: working directory to execute LEMS simulation in
    :type exec_in_dir: str
    :param only_generate_scripts: toggle whether only the runner script should be generated
    :type only_generate_scripts: bool
    :param compile_mods: toggle whether generated mod files should be compiled
    :type compile_mods: bool
    :param verbose: toggle whether jnml should print verbose information
    :type verbose: bool
    :param exit_on_fail: toggle whether command should exit if jnml fails
    :type exit_on_fail: bool
    :param cleanup: toggle whether the directory should be cleaned of generated files after run completion
    :type cleanup: bool
    :param realtime_output: toggle whether realtime output should be shown
    :type realtime_output: bool
    """

    logger.info(
        "Loading LEMS file: {} and running with jNeuroML_NEURON".format(lems_file_name)
    )

    post_args = " -neuron"
    if not only_generate_scripts:  # and jnml_runs_neuron:
        post_args += " -run"
    if compile_mods:
        post_args += " -compile"

    post_args += _gui_string(nogui)
    post_args += _include_string(paths_to_include)

    t_run = datetime.now()
    if skip_run:
        success = True
    else:
        # Fix PYTHONPATH for NEURON: has been an issue on HBP Collaboratory...
        if "PYTHONPATH" not in os.environ:
            os.environ["PYTHONPATH"] = ""
        for path in sys.path:
            if path + ":" not in os.environ["PYTHONPATH"]:
                os.environ["PYTHONPATH"] = "%s:%s" % (path, os.environ["PYTHONPATH"])

        logger.debug("PYTHONPATH for NEURON: {}".format(os.environ["PYTHONPATH"]))

        if realtime_output:
            success = run_jneuroml_with_realtime_output(
                "",
                lems_file_name,
                post_args,
                max_memory=max_memory,
                exec_in_dir=exec_in_dir,
                verbose=verbose,
                exit_on_fail=exit_on_fail,
            )
            logger.debug("PYTHONPATH for NEURON: {}".format(os.environ["PYTHONPATH"]))
        else:
            success = run_jneuroml(
                "",
                lems_file_name,
                post_args,
                max_memory=max_memory,
                exec_in_dir=exec_in_dir,
                verbose=verbose,
                report_jnml_output=verbose,
                exit_on_fail=exit_on_fail,
            )

        """
        TODO: Work in progress!!!
        if not jnml_runs_neuron:
          logger.info("Running...")
          from LEMS_NML2_Ex5_DetCell_nrn import NeuronSimulation
          ns = NeuronSimulation(tstop=300, dt=0.01, seed=123456789)
          ns.run()
        """

    if not success:
        return False

    if load_saved_data:
        return reload_saved_data(
            lems_file_name,
            base_dir=exec_in_dir,
            t_run=t_run,
            plot=plot,
            show_plot_already=show_plot_already,
            simulator="jNeuroML_NEURON",
            reload_events=reload_events,
            remove_dat_files_after_load=cleanup,
        )
    else:
        return True


def run_lems_with_jneuroml_netpyne(
    lems_file_name: str,
    paths_to_include: typing.List[str] = [],
    max_memory: str = DEFAULTS["default_java_max_memory"],
    skip_run: bool = False,
    nogui: bool = False,
    num_processors: int = 1,
    load_saved_data: bool = False,
    reload_events: bool = False,
    plot: bool = False,
    show_plot_already: bool = True,
    exec_in_dir: str = ".",
    only_generate_scripts: bool = False,
    only_generate_json: bool = False,
    verbose: bool = DEFAULTS["v"],
    exit_on_fail: bool = True,
    return_string: bool = False,
    cleanup: bool = False,
) -> typing.Union[
    bool, typing.Tuple[bool, str], typing.Union[dict, typing.Tuple[dict, dict]]
]:
    """Run LEMS file with the NEURON simulator

    Tip: set `skip_run=True` to only parse the LEMS file but not run the simulation.

    :param lems_file_name: name of LEMS file to run
    :type lems_file_name: str
    :param paths_to_include: additional directory paths to include (for other NML/LEMS files, for example)
    :type paths_to_include: list(str)
    :param max_memory: maximum memory allowed for use by the JVM
    :type max_memory: bool
    :param skip_run: toggle whether run should be skipped, if skipped, file will only be parsed
    :type skip_run: bool
    :param nogui: toggle whether jnml GUI should be shown
    :type nogui: bool
    :param num_processors: number of processors to use for running NetPyNE
    :type num_processors: int
    :param load_saved_data: toggle whether any saved data should be loaded
    :type load_saved_data: bool
    :param reload_events: toggle whether events should be reloaded
    :type reload_events: bool
    :param plot: toggle whether specified plots should be plotted
    :type plot: bool
    :param show_plot_already: toggle whether prepared plots should be shown
    :type show_plot_already: bool
    :param exec_in_dir: working directory to execute LEMS simulation in
    :type exec_in_dir: str
    :param only_generate_scripts: toggle whether only the runner script should be generated
    :type only_generate_scripts: bool
    :param verbose: toggle whether jnml should print verbose information
    :type verbose: bool
    :param exit_on_fail: toggle whether command should exit if jnml fails
    :type exit_on_fail: bool
    :param return_string: toggle whether command output string should be returned
    :type return_string: bool
    :param cleanup: toggle whether the directory should be cleaned of generated files after run completion
    :type cleanup: bool
    :returns: either a bool, or a Tuple (bool, str) depending on the value of
        return_string: True of jnml ran successfully, False if not; along with the
        output of the command. If load_saved_data is True, it returns a dict
        with the data

    """

    logger.info(
        "Loading LEMS file: {} and running with jNeuroML_NetPyNE".format(lems_file_name)
    )

    post_args = " -netpyne"

    if num_processors != 1:
        post_args += " -np %i" % num_processors
    if not only_generate_scripts and not only_generate_json:
        post_args += " -run"
    if only_generate_json:
        post_args += " -json"

    post_args += _gui_string(nogui)
    post_args += _include_string(paths_to_include)

    t_run = datetime.now()
    if skip_run:
        success = True
    else:
        if return_string is True:
            (success, output_string) = run_jneuroml(
                "",
                lems_file_name,
                post_args,
                max_memory=max_memory,
                exec_in_dir=exec_in_dir,
                verbose=verbose,
                exit_on_fail=exit_on_fail,
                return_string=True,
            )
        else:
            success = run_jneuroml(
                "",
                lems_file_name,
                post_args,
                max_memory=max_memory,
                exec_in_dir=exec_in_dir,
                verbose=verbose,
                exit_on_fail=exit_on_fail,
                return_string=False,
            )

    if not success and return_string is True:
        return False, output_string
    if not success and return_string is False:
        return False

    if load_saved_data:
        return reload_saved_data(
            lems_file_name,
            base_dir=exec_in_dir,
            t_run=t_run,
            plot=plot,
            show_plot_already=show_plot_already,
            simulator="jNeuroML_NetPyNE",
            reload_events=reload_events,
            remove_dat_files_after_load=cleanup,
        )

    if return_string is True:
        return True, output_string

    return True


# TODO: need to enable run with Brian2!
def run_lems_with_jneuroml_brian2(
    lems_file_name: str,
    paths_to_include: typing.List[str] = [],
    max_memory: str = DEFAULTS["default_java_max_memory"],
    skip_run: bool = False,
    nogui: bool = False,
    load_saved_data: bool = False,
    reload_events: bool = False,
    plot: bool = False,
    show_plot_already: bool = True,
    exec_in_dir: str = ".",
    verbose: bool = DEFAULTS["v"],
    exit_on_fail: bool = True,
    cleanup: bool = False,
) -> typing.Union[bool, typing.Union[dict, typing.Tuple[dict, dict]]]:
    """Run LEMS file with the NEURON simulator

    Tip: set `skip_run=True` to only parse the LEMS file but not run the simulation.

    :param lems_file_name: name of LEMS file to run
    :type lems_file_name: str
    :param paths_to_include: additional directory paths to include (for other NML/LEMS files, for example)
    :type paths_to_include: list(str)
    :param max_memory: maximum memory allowed for use by the JVM
    :type max_memory: bool
    :param skip_run: toggle whether run should be skipped, if skipped, file will only be parsed
    :type skip_run: bool
    :param nogui: toggle whether jnml GUI should be shown
    :type nogui: bool
    :param load_saved_data: toggle whether any saved data should be loaded
    :type load_saved_data: bool
    :param reload_events: toggle whether events should be reloaded
    :type reload_events: bool
    :param plot: toggle whether specified plots should be plotted
    :type plot: bool
    :param show_plot_already: toggle whether prepared plots should be shown
    :type show_plot_already: bool
    :param exec_in_dir: working directory to execute LEMS simulation in
    :type exec_in_dir: str
    :param verbose: toggle whether jnml should print verbose information
    :type verbose: bool
    :param exit_on_fail: toggle whether command should exit if jnml fails
    :type exit_on_fail: bool
    :param cleanup: toggle whether the directory should be cleaned of generated files after run completion
    :type cleanup: bool
    """

    logger.info(
        "Loading LEMS file: {} and running with jNeuroML_Brian2".format(lems_file_name)
    )

    post_args = " -brian2"

    # post_args += _gui_string(nogui)
    # post_args += _include_string(paths_to_include)

    t_run = datetime.now()
    if skip_run:
        success = True
    else:
        success = run_jneuroml(
            "",
            lems_file_name,
            post_args,
            max_memory=max_memory,
            exec_in_dir=exec_in_dir,
            verbose=verbose,
            exit_on_fail=exit_on_fail,
        )

        old_sys_args = [a for a in sys.argv]
        sys.argv[1] = "-nogui"  # To supress gui for brian simulation...
        logger.info(
            "Importing generated Brian2 python file (changed args from {} to {})".format(
                old_sys_args, sys.argv
            )
        )
        brian2_py_name = lems_file_name.replace(".xml", "_brian2")
        exec("import %s" % brian2_py_name)
        sys.argv = old_sys_args
        logger.info("Finished Brian2 simulation, back to {}".format(sys.argv))

    if not success:
        return False

    if load_saved_data:
        return reload_saved_data(
            lems_file_name,
            base_dir=exec_in_dir,
            t_run=t_run,
            plot=plot,
            show_plot_already=show_plot_already,
            simulator="jNeuroML_Brian2",
            reload_events=reload_events,
            remove_dat_files_after_load=cleanup,
        )
    else:
        return True


def run_lems_with_eden(
    lems_file_name: str,
    load_saved_data: bool = False,
    reload_events: bool = False,
    verbose: bool = DEFAULTS["v"],
) -> typing.Union[bool, typing.Union[dict, typing.Tuple[dict, dict]]]:
    """Run LEMS file with the EDEN simulator

    :param lems_file_name: name of LEMS file to run
    :type lems_file_name: str
    :param load_saved_data: toggle whether any saved data should be loaded
    :type load_saved_data: bool
    :param reload_events: toggle whether events should be reloaded
    :type reload_events: bool
    :param verbose: toggle whether to print verbose information
    :type verbose: bool
    """

    import eden_simulator

    logger.info(
        "Running a simulation of %s in EDEN v%s"
        % (
            lems_file_name,
            (
                eden_simulator.__version__
                if hasattr(eden_simulator, "__version__")
                else "???"
            ),
        )
    )

    results = eden_simulator.runEden(lems_file_name)

    if verbose:
        logger.info(
            "Completed simulation in EDEN, saved results: %s" % (results.keys())
        )

    if load_saved_data:
        logger.warning("Event saving is not yet supported in EDEN!!")
        return results, {}
    elif load_saved_data:
        return results
    else:
        return True


def _gui_string(nogui: bool) -> str:
    """Return the gui string for jnml

    :param nogui: toggle whether GUI should be used or not
    :type nogui: bool
    :returns: gui  string or empty string
    """
    return " -nogui" if nogui else ""


def _include_string(
    paths_to_include: typing.Union[str, typing.Tuple[str], typing.List[str]]
) -> str:
    """Convert a path or list of paths into an include string to be used by jnml.
    :param paths_to_include: path or list or tuple of paths to be included
    :type paths_to_include: str or list(str) or tuple(str)
    :returns: include string to be used with jnml.
    """
    if paths_to_include:
        if type(paths_to_include) is str:
            paths_to_include = [paths_to_include]
    if type(paths_to_include) in (tuple, list):
        result = " -I '%s'" % ":".join(paths_to_include)
    else:
        result = ""
    return result


def run_jneuroml(
    pre_args: str,
    target_file: str,
    post_args: str,
    max_memory: str = DEFAULTS["default_java_max_memory"],
    exec_in_dir: str = ".",
    verbose: bool = DEFAULTS["v"],
    report_jnml_output: bool = True,
    exit_on_fail: bool = False,
    return_string: bool = False,
) -> typing.Union[typing.Tuple[bool, str], bool]:
    """Run jnml with provided arguments.

    :param pre_args: pre-file name arguments
    :type pre_args: list of strings
    :param target_file: LEMS or NeuroML file to run jnml on
    :type target_file: str
    :param max_memory: maximum memory allowed for use by the JVM
        Note that the default value of this can be overridden using the
        JNML_MAX_MEMORY_LOCAL environment variable
    :type max_memory: str
    :param exec_in_dir: working directory to execute LEMS simulation in
    :type exec_in_dir: str
    :param verbose: toggle whether jnml should print verbose information
    :type verbose: bool
    :param report_jnml_output: toggle whether jnml output should be printed
    :type report_jnml_output: bool
    :param exit_on_fail: toggle whether command should exit if jnml fails
    :type exit_on_fail: bool
    :param return_string: toggle whether the output string should be returned
    :type return_string: bool

    :returns: either a bool, or a Tuple (bool, str) depending on the value of
        return_string: True of jnml ran successfully, False if not; along with the
        output of the command

    """
    logger.debug(
        "Running jnml on %s with pre args: [%s], post args: [%s], in dir: %s, verbose: %s, report: %s, exit on fail: %s"
        % (
            target_file,
            pre_args,
            post_args,
            exec_in_dir,
            verbose,
            report_jnml_output,
            exit_on_fail,
        )
    )
    if post_args and "nogui" in post_args and not os.name == "nt":
        pre_jar = " -Djava.awt.headless=true"
    else:
        pre_jar = ""

    jar_path = pyneuroml.utils.misc.get_path_to_jnml_jar()
    output = ""
    retcode = -1

    try:
        command = f'java -Xmx{max_memory} {pre_jar} -jar  "{jar_path}" {pre_args} {target_file} {post_args}'
        retcode, output = execute_command_in_dir(
            command, exec_in_dir, verbose=verbose, prefix=" jNeuroML >>  "
        )

        if retcode != 0:
            if exit_on_fail:
                logger.error("execute_command_in_dir returned with output: %s" % output)
                sys.exit(retcode)
            else:
                if return_string:
                    return (False, output)
                else:
                    return False

        if report_jnml_output:
            logger.debug(
                "Successfully ran the following command using pyNeuroML v%s: \n    %s"
                % (__version__, command)
            )
            logger.debug("Output:\n\n%s" % output)

    #  except KeyboardInterrupt as e:
    #    raise e

    except Exception as e:
        logger.error("*** Execution of jnml has failed! ***")
        logger.error("Error:  %s" % e)
        logger.error("*** Command: %s ***" % command)
        logger.error("Output: %s" % output)
        if exit_on_fail:
            sys.exit(UNKNOWN_ERR)
        else:
            if return_string:
                return (False, output)
            else:
                return False
    if return_string:
        return (True, output)
    else:
        return True


# TODO: Refactorinng
def run_jneuroml_with_realtime_output(
    pre_args: str,
    target_file: str,
    post_args: str,
    max_memory: str = DEFAULTS["default_java_max_memory"],
    exec_in_dir: str = ".",
    verbose: bool = DEFAULTS["v"],
    exit_on_fail: bool = True,
) -> bool:
    # XXX: Only tested with Linux
    """Run jnml with provided arguments with realtime output.

    NOTE: this has only been tested on Linux.

    :param pre_args: pre-file name arguments
    :type pre_args: list of strings
    :param target_file: LEMS or NeuroML file to run jnml on
    :type target_file: str
    :param max_memory: maximum memory allowed for use by the JVM
    :type max_memory: bool
    :param exec_in_dir: working directory to execute LEMS simulation in
    :type exec_in_dir: str
    :param verbose: toggle whether jnml should print verbose information
    :type verbose: bool
    :param exit_on_fail: toggle whether command should exit if jnml fails
    :type exit_on_fail: bool
    """
    if post_args and "nogui" in post_args and not os.name == "nt":
        pre_jar = " -Djava.awt.headless=true"
    else:
        pre_jar = ""
    jar_path = pyneuroml.utils.misc.get_path_to_jnml_jar()

    command = ""
    command_success = False

    try:
        command = 'java -Xmx%s %s -jar  "%s" %s "%s" %s' % (
            max_memory,
            pre_jar,
            jar_path,
            pre_args,
            target_file,
            post_args,
        )
        command_success = execute_command_in_dir_with_realtime_output(
            command, exec_in_dir, verbose=verbose, prefix=" jNeuroML >>  "
        )

    except KeyboardInterrupt as e:
        raise e
    except:
        logger.error("*** Execution of jnml has failed! ***")
        logger.error("*** Command: %s ***" % command)
        if exit_on_fail:
            sys.exit(UNKNOWN_ERR)
        else:
            return False

    return command_success


def execute_command_in_dir_with_realtime_output(
    command: str,
    directory: str,
    verbose: bool = DEFAULTS["v"],
    prefix: str = "Output: ",
    env: typing.Optional[str] = None,
) -> bool:
    # NOTE: Only tested with Linux
    """Run a command in a given directory with real time output.

    NOTE: this has only been tested on Linux.

    :param command: command to run
    :type command: str
    :param directory: directory to run command in
    :type directory: str
    :param verbose: toggle verbose output
    :type verbose: bool
    :param prefix: string to prefix output with
    :type prefix: str
    :param env: environment variables to be used
    :type env: str
    """
    if os.name == "nt":
        directory = os.path.normpath(directory)

    print("####################################################################")
    print("# pyNeuroML executing: (%s) in directory: %s" % (command, directory))
    if env is not None:
        print("# Extra env variables %s" % (env))
    print("####################################################################")

    p = None
    try:
        p = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            cwd=directory,
            env=env,
            universal_newlines=True,
        )
        with p.stdout:
            for line in iter(p.stdout.readline, ""):
                print("# %s" % line.strip())
        p.wait()  # wait for the subprocess to exit

        print("####################################################################")
    except KeyboardInterrupt as e:
        logger.error("*** Command interrupted: \n       %s" % command)
        if p:
            p.kill()
        raise e
    except Exception as e:
        print("# Exception occured: %s" % (e))
        print("# More...")
        print(traceback.format_exc())
        print("####################################################################")
        raise e

    if not p.returncode == 0:
        logger.critical(
            "*** Problem running command (return code: %s): \n       %s"
            % (p.returncode, command)
        )

    return p.returncode == 0


def execute_command_in_dir(
    command: str,
    directory: str,
    verbose: bool = DEFAULTS["v"],
    prefix: str = "Output: ",
    env: Optional[typing.Any] = None,
) -> typing.Tuple[int, str]:
    """Execute a command in specific working directory

    :param command: command to run
    :type command: str
    :param directory: directory to run command in
    :type directory: str
    :param verbose: toggle verbose output
    :type verbose: bool
    :param prefix: string to prefix console output with
    :type prefix: str
    :param env: environment variables to be used
    :type env: str
    """
    return_string = ""  # type: typing.Union[bytes, str]
    if os.name == "nt":
        directory = os.path.normpath(directory)

    logger.info("Executing: (%s) in directory: %s" % (command, directory))
    if env is not None:
        logger.debug("Extra env variables %s" % (env))

    try:
        if os.name == "nt":
            return_string = subprocess.check_output(
                command, cwd=directory, shell=True, env=env, close_fds=False
            )
        else:
            return_string = subprocess.check_output(
                command,
                cwd=directory,
                shell=True,
                stderr=subprocess.STDOUT,
                env=env,
                close_fds=True,
            )

        return_string = return_string.decode("utf-8")  # For Python 3

        logger.info("Command completed successfully!")
        if verbose:
            logger.info(
                "Output: \n %s%s"
                % (prefix, return_string.replace("\n", "\n " + prefix))
            )
        return (0, return_string)

    except AttributeError:
        # For python 2.6...
        logger.warning("Assuming Python 2.6...")

        return_string = subprocess.Popen(
            command, cwd=directory, shell=True, stdout=subprocess.PIPE
        ).communicate()[0]
        return return_string.decode("utf-8")

    except subprocess.CalledProcessError as e:
        logger.critical("*** Problem running command: \n       %s" % e)
        logger.critical(
            "%s%s" % (prefix, e.output.decode().replace("\n", "\n" + prefix))
        )
        return (e.returncode, e.output.decode())
    except Exception as e:
        logger.critical("*** Unknown problem running command: %s" % e)
        return (-1, str(e))


def reload_saved_data(
    lems_file_name: str,
    base_dir: str = ".",
    t_run: datetime = datetime(1900, 1, 1),
    plot: bool = False,
    show_plot_already: bool = True,
    simulator: typing.Optional[str] = None,
    reload_events: bool = False,
    verbose: bool = DEFAULTS["v"],
    remove_dat_files_after_load: bool = False,
) -> typing.Union[dict, typing.Tuple[dict, dict]]:
    """Reload data saved from previous LEMS simulation run.

    :param lems_file_name: name of LEMS file that was used to generate the data
    :type lems_file_name: str
    :param base_dir: directory to run in
    :type base_dir: str
    :param t_run: time of run
    :type t_run: datetime
    :param plot: toggle plotting
    :type plot: bool
    :param show_plot_already: toggle if plots should be shown
    :type show_plot_already: bool
    :param simulator: simulator that was used to generate data
    :type simulator: str
    :param reload_event: toggle whether events should be loaded
    :type reload_event: bool
    :param verbose: toggle verbose output
    :type verbose: bool
    :param remove_dat_files_after_load: toggle if data files should be deleted after they've been loaded
    :type remove_dat_files_after_load: bool


    TODO: remove unused vebose argument (needs checking to see if is being
    used in other places)
    """
    if not os.path.isfile(lems_file_name):
        real_lems_file = os.path.realpath(os.path.join(base_dir, lems_file_name))
    else:
        real_lems_file = os.path.realpath(lems_file_name)

    logger.debug(
        "Reloading data specified in LEMS file: %s (%s), base_dir: %s, cwd: %s; plotting %s"
        % (lems_file_name, real_lems_file, base_dir, os.getcwd(), show_plot_already)
    )

    # Could use pylems to parse all this...
    traces = {}  # type: dict
    events = {}  # type: dict

    if plot:
        import matplotlib.pyplot as plt

    base_lems_file_path = os.path.dirname(os.path.realpath(lems_file_name))
    tree = etree.parse(real_lems_file)

    sim = tree.getroot().find("Simulation")
    ns_prefix = ""

    possible_prefixes = ["{http://www.neuroml.org/lems/0.7.2}"]
    if sim is None:
        # print(tree.getroot().nsmap)
        # print(tree.getroot().getchildren())
        for pre in possible_prefixes:
            for comp in tree.getroot().findall(pre + "Component"):
                if comp.attrib["type"] == "Simulation":
                    ns_prefix = pre
                    sim = comp

    if reload_events:
        event_output_files = sim.findall(ns_prefix + "EventOutputFile")
        for i, of in enumerate(event_output_files):
            name = of.attrib["fileName"]
            file_name = os.path.join(base_dir, name)
            if not os.path.isfile(file_name):  # If not relative to the LEMS file...
                file_name = os.path.join(base_lems_file_path, name)

            # if not os.path.isfile(file_name): # If not relative to the LEMS file...
            #    file_name = os.path.join(os.getcwd(),name)
            # ... try relative to cwd.
            # if not os.path.isfile(file_name): # If not relative to the LEMS file...
            #    file_name = os.path.join(os.getcwd(),'NeuroML2','results',name)
            # ... try relative to cwd in NeuroML2/results subdir.
            if not os.path.isfile(file_name):  # If not relative to the base dir...
                raise OSError(
                    ("Could not find simulation output " "file %s" % file_name)
                )
            format = of.attrib["format"]
            logger.info(
                "Loading saved events from %s (format: %s)" % (file_name, format)
            )
            selections = {}
            for col in of.findall(ns_prefix + "EventSelection"):
                id = int(col.attrib["id"])
                select = col.attrib["select"]
                events[select] = []
                selections[id] = select

            with open(file_name) as f:
                for line in f:
                    values = line.split()
                    if format == "TIME_ID":
                        t = float(values[0])
                        id = int(values[1])
                    elif format == "ID_TIME":
                        id = int(values[0])
                        t = float(values[1])
                    logger.debug(
                        "Found a event in cell %s (%s) at t = %s"
                        % (id, selections[id], t)
                    )
                    events[selections[id]].append(t)

            if remove_dat_files_after_load:
                logger.warning(
                    "Removing file %s after having loading its data!" % file_name
                )
                os.remove(file_name)

    output_files = sim.findall(ns_prefix + "OutputFile")
    n_output_files = len(output_files)
    if plot:
        rows = int(max(1, math.ceil(n_output_files / float(3))))
        columns = min(3, n_output_files)
        fig, ax = plt.subplots(
            rows, columns, sharex=True, figsize=(8 * columns, 4 * rows)
        )
        if n_output_files > 1:
            ax = ax.ravel()

    for i, of in enumerate(output_files):
        traces["t"] = []
        name = of.attrib["fileName"]
        file_name = os.path.join(base_dir, name)

        if not os.path.isfile(file_name):  # If not relative to the LEMS file...
            file_name = os.path.join(base_lems_file_path, name)

        if not os.path.isfile(file_name):  # If not relative to the LEMS file...
            file_name = os.path.join(os.getcwd(), name)

            # ... try relative to cwd.
        if not os.path.isfile(file_name):  # If not relative to the LEMS file...
            file_name = os.path.join(os.getcwd(), "NeuroML2", "results", name)
            # ... try relative to cwd in NeuroML2/results subdir.
        if not os.path.isfile(file_name):  # If not relative to the LEMS file...
            raise OSError(("Could not find simulation output " "file %s" % file_name))
        t_file_mod = datetime.fromtimestamp(os.path.getmtime(file_name))
        if t_file_mod < t_run:
            raise Exception(
                "Expected output file %s has not been modified since "
                "%s but the simulation was run later at %s."
                % (file_name, t_file_mod, t_run)
            )

        logger.debug(
            "Loading saved data from %s%s"
            % (file_name, " (%s)" % simulator if simulator else "")
        )

        cols = []
        cols.append("t")
        for col in of.findall(ns_prefix + "OutputColumn"):
            quantity = col.attrib["quantity"]
            traces[quantity] = []
            cols.append(quantity)

        with open(file_name) as f:
            for line in f:
                values = line.split()
                for vi in range(len(values)):
                    traces[cols[vi]].append(float(values[vi]))

        if remove_dat_files_after_load:
            logger.warning(
                "Removing file %s after having loading its data!" % file_name
            )
            os.remove(file_name)

        if plot:
            info = "Data loaded from %s%s" % (
                file_name,
                " (%s)" % simulator if simulator else "",
            )
            logger.warning("Reloading: %s" % info)
            plt.get_current_fig_manager().set_window_title(info)

            legend = False
            for key in cols:
                if n_output_files > 1:
                    ax_ = ax[i]
                else:
                    ax_ = ax
                ax_.set_xlabel("Time (ms)")
                ax_.set_ylabel("(SI units...)")
                ax_.xaxis.grid(True)
                ax_.yaxis.grid(True)

                if key != "t":
                    ax_.plot(traces["t"], traces[key], label=key)
                    logger.debug("Adding trace for: %s, from: %s" % (key, file_name))
                    ax_.used = True
                    legend = True

                if legend:
                    if n_output_files > 1:
                        ax_.legend(
                            loc="upper right", fancybox=True, shadow=True, ncol=4
                        )  # ,bbox_to_anchor=(0.5, -0.05))
                    else:
                        ax_.legend(
                            loc="upper center",
                            bbox_to_anchor=(0.5, -0.05),
                            fancybox=True,
                            shadow=True,
                            ncol=4,
                        )

    #  print(traces.keys())

    if plot and show_plot_already:
        if n_output_files > 1:
            ax_ = ax
        else:
            ax_ = [ax]
        for axi in ax_:
            if not hasattr(axi, "used") or not axi.used:
                axi.axis("off")
        plt.tight_layout()
        plt.show()

    if reload_events:
        return traces, events
    else:
        return traces


def generate_sim_scripts_in_folder(
    engine: str,
    lems_file_name: str,
    root_dir: typing.Optional[str] = None,
    run_dir: typing.Optional[str] = None,
    generated_files_dir_name: typing.Optional[str] = None,
    *engine_args: typing.Any,
    **engine_kwargs: typing.Any,
) -> str:
    """Generate simulation scripts in a new folder.

    This method copies the model files and generates the simulation engine
    specific files (runner script for NEURON and mod files, for example) for
    the provided engine in a new folder. This is useful when running
    simulations on remote systems like a cluster or NSG which may not have the
    necessary dependencies installed to generate these scripts. One can then
    copy the folder to the remote system and run simulations there.

    While copying the model files is not compulsory, we do it to ensure that
    there's a clear correspondence between the set of model files and the
    generated simulation files generated from them. This is also allows easy
    inspection of model files for debugging.

    .. versionadded:: 1.0.14

    :param engine: name of engine: suffixes of the run_lems_with functions
    :type engine: str
    :param lems_file_name: name of LEMS simulation file
    :type lems_file_name: str
    :param root_dir: directory in which LEMS simulation file lives
        Any included files must be relative to this main directory
    :type root_dir: str
    :param run_dir: directory in which model files are copied and backend
        specific files are generated.

        By default, this is the directory that the command is run from (".")

        It is good practice to separate directories where simulations are run
        from the source of the model/simulations.
    :type run_dir: str
    :param generated_files_dir_name: name of folder to move generated files to
        if not provided, a `_generated` suffix is added to the main directory
        that is created
    :type generated_files_dir_name: str
    :param engine_args: positional args to be passed to the engine runner
        function
    :param engine_kwargs: keyword args to be be passed to the engine runner
        function
    :returns: name of directory that was created
    :rtype: str
    """
    supported_engines = ["jneuroml_neuron", "jneuroml_netpyne"]
    if engine not in supported_engines:
        print(f"Engine {engine} is not currently supported on NSG")
        print(f"Supported engines are: {supported_engines}")
        return None

    logger.debug(f"Engine is {engine}")

    if run_dir is None:
        run_dir = "."

    if root_dir is None:
        root_dir = "."

    tdir = pyneuroml.utils.get_pyneuroml_tempdir(rootdir=run_dir, prefix="pyneuroml")
    os.mkdir(tdir)

    if len(Path(lems_file_name).parts) > 1:
        raise RuntimeError(
            "Please only provide the name of the file here and use rootdir to provide the folder it lives in"
        )

    logger.debug("Getting list of model files")
    model_file_list = []  # type: list
    lems_def_dir = None
    lems_def_dir = pyneuroml.utils.get_model_file_list(
        lems_file_name, model_file_list, root_dir, lems_def_dir
    )

    root_dir = str(Path(root_dir).absolute())

    logger.debug(f"Model file list is {model_file_list}")

    for model_file in model_file_list:
        logger.debug(f"Copying: {root_dir}/{model_file} -> {tdir + '/' + model_file}")
        # if model file has directory structures in it, recreate the dirs in
        # the temporary directory
        if len(model_file.split("/")) > 1:
            # throw error if files in parent directories are referred to
            if "../" in model_file:
                raise ValueError(
                    """
                    Cannot handle parent directories because we
                    cannot create these directories correctly in
                    the temporary location. Please re-organize
                    your code such that all included files are in
                    sub-directories of the root directory where the
                    main file resides.
                    """
                )

            model_file_path = pathlib.Path(tdir + "/" + model_file)
            parent = model_file_path.parent
            parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root_dir + "/" + model_file, tdir + "/" + model_file)

    if lems_def_dir is not None:
        logger.info(f"Removing LEMS definitions directory {lems_def_dir}")
        shutil.rmtree(lems_def_dir)

    cwd = Path.cwd()
    os.chdir(tdir)
    logger.info(f"Working in {tdir}")
    start_time = time.time() - 1.0

    if engine == "jneuroml_neuron":
        run_lems_with(
            engine,
            lems_file_name=Path(lems_file_name).name,
            compile_mods=False,
            only_generate_scripts=True,
            *engine_args,
            **engine_kwargs,
        )
    elif engine == "jneuroml_netpyne":
        run_lems_with(
            engine,
            lems_file_name=Path(lems_file_name).name,
            only_generate_scripts=True,
            *engine_args,
            **engine_kwargs,
        )

    generated_files = pyneuroml.utils.get_files_generated_after(
        start_time, ignore_suffixes=["xml", "nml"]
    )

    # For NetPyNE, the channels are converted to NEURON mod files, but the
    # network and cells are imported from the nml files.
    # So we include all the model files too.
    if engine == "jneuroml_netpyne":
        generated_files.extend(model_file_list)

    logger.debug(f"Generated files are: {generated_files}")

    if generated_files_dir_name is None:
        generated_files_dir_name = Path(tdir).name + "_generated"
    logger.debug(
        f"Creating directory and moving generated files to it: {generated_files_dir_name}"
    )

    for f in generated_files:
        fpath = pathlib.Path(f)
        moved_path = generated_files_dir_name / fpath
        # use os.renames because pathlib.Path.rename does not move
        # recursively and so cannot move files within directories
        os.renames(fpath, moved_path)

    # return to original directory
    # doesn't affect scripts much, but does affect our tests
    os.chdir(str(cwd))

    return tdir
