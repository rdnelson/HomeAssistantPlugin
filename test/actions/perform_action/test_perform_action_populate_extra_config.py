import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

absolute_mock_path = str(Path(__file__).parent.parent.parent / "stream_controller_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from HomeAssistantPlugin.actions.perform_action.perform_action import PerformAction


class TestPerformActionPopulateExtraConfig(unittest.TestCase):
    """_populate_extra_config runs on the main thread (via get_config_rows /
    _on_backend_ready) and must load the action combo."""

    @patch('HomeAssistantPlugin.actions.perform_action.perform_action.BaseCore.__init__')
    @patch('HomeAssistantPlugin.actions.perform_action.perform_action.BaseCore._populate_extra_config')
    @patch.object(PerformAction, '_load_actions')
    def test_populate_extra_config_loads_actions(self, load_actions_mock, super_populate_mock, _):
        instance = PerformAction()

        instance._populate_extra_config()

        super_populate_mock.assert_called_once()
        load_actions_mock.assert_called_once()
