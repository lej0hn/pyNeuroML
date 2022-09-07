#!/usr/bin/env python3
"""
Test general utils

File: tests/utils/test_utils.py

Copyright 2022 NeuroML contributors
"""

import unittest
import tempfile
import neuroml
from neuroml import IonChannel
import pyneuroml as pynml
from pyneuroml.utils import *
from neuroml import NeuroMLDocument


class UtilsTestCase(unittest.TestCase):

    """Test the Utils module"""

    def test_component_factory(self):
        "Test the component factory."

        nml_doc = component_factory("NeuroMLDocument", id="emptydocument")
        iaf_cell = component_factory(
            "IafCell",
            id="test_cell",
            leak_reversal="-50 mV",
            thresh="-55mV",
            reset="-70 mV",
            C="0.2nF",
            leak_conductance="0.01uS",
        )
        nml_doc.add(iaf_cell)

        with tempfile.NamedTemporaryFile() as test_file:
            self.assertTrue(
                pynml.pynml.write_neuroml2_file(nml_doc, test_file.name, validate=True)
            )

    @unittest.expectedFailure
    def test_component_factory_should_fail(self):
        "Test the component factory."

        nml_doc = component_factory("NeuroMLDocument", id="emptydocument")
        iaf_cell = component_factory(
            "IafCell",
            id="test_cell",
        )
        nml_doc.add(iaf_cell)

        with tempfile.NamedTemporaryFile() as test_file:
            self.assertTrue(
                pynml.pynml.write_neuroml2_file(nml_doc, test_file.name, validate=True)
            )

    def test_component_argument_list_checker(self):
        """Test the check_component_type_arg_list utility function"""
        nml_doc = neuroml.nml.nml.NeuroMLDocument()
        with self.assertRaises(ValueError) as cm:
            check_component_type_arg_list(nml_doc, random_argument="nope")
        print(cm.exception)
        check_component_type_arg_list(nml_doc, id="yep")