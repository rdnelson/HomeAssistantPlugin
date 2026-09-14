import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

absolute_mock_path = str(Path(__file__).parent.parent.parent.parent / "stream_controller_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from HomeAssistantPlugin.actions.cores.base_core.base_core import BaseCore


class TestBaseCoreOnReady(unittest.TestCase):
    """on_ready runs (possibly off the main thread) so it must only render the
    key and touch the thread-safe backend - never the config-editor widgets.
    Config-UI population happens in get_config_rows / _on_backend_ready."""

    @patch.object(BaseCore, "create_ui_elements")
    @patch.object(BaseCore, "_create_event_assigner")
    @patch.object(BaseCore, "refresh")
    @patch.object(BaseCore, "_populate_config_ui")
    @patch.object(BaseCore, "_load_domains")
    @patch.object(BaseCore, "_load_entities")
    @patch('HomeAssistantPlugin.actions.cores.base_core.base_core.migrate_settings')
    def test_on_ready_no_entity(self, migrate_settings_mock, load_entities_mock, load_domains_mock,
                                populate_config_ui_mock, refresh_mock, _, __):
        track_entity = True

        settings_implementation = Mock()
        settings_implementation.return_value = settings_implementation
        settings_implementation.get_entity.return_value = None

        instance = BaseCore(settings_implementation, track_entity)
        instance.on_ready()

        migrate_settings_mock.assert_called_once_with(instance)
        instance.plugin_base.backend.add_action_ready_callback.assert_called_once_with(instance._on_backend_ready)
        settings_implementation.get_entity.assert_called_once()
        instance.plugin_base.backend.add_tracked_entity.assert_not_called()
        refresh_mock.assert_called_once()
        # config-editor widgets must not be touched from on_ready (may be off-thread)
        load_entities_mock.assert_not_called()
        load_domains_mock.assert_not_called()
        populate_config_ui_mock.assert_not_called()

    @patch.object(BaseCore, "create_ui_elements")
    @patch.object(BaseCore, "_create_event_assigner")
    @patch.object(BaseCore, "refresh")
    @patch.object(BaseCore, "_populate_config_ui")
    @patch.object(BaseCore, "_load_domains")
    @patch.object(BaseCore, "_load_entities")
    @patch('HomeAssistantPlugin.actions.cores.base_core.base_core.migrate_settings')
    def test_on_ready_entity_not_tracked(self, migrate_settings_mock, load_entities_mock, load_domains_mock,
                                         populate_config_ui_mock, refresh_mock, _, __):
        track_entity = False

        settings_implementation = Mock()
        settings_implementation.return_value = settings_implementation
        settings_implementation.get_entity.return_value = "entity"

        instance = BaseCore(settings_implementation, track_entity)
        instance.on_ready()

        migrate_settings_mock.assert_called_once_with(instance)
        instance.plugin_base.backend.add_action_ready_callback.assert_called_once_with(instance._on_backend_ready)
        settings_implementation.get_entity.assert_called_once()
        instance.plugin_base.backend.add_tracked_entity.assert_not_called()
        refresh_mock.assert_called_once()
        load_entities_mock.assert_not_called()
        load_domains_mock.assert_not_called()
        populate_config_ui_mock.assert_not_called()

    @patch.object(BaseCore, "create_ui_elements")
    @patch.object(BaseCore, "_create_event_assigner")
    @patch.object(BaseCore, "refresh")
    @patch.object(BaseCore, "_populate_config_ui")
    @patch.object(BaseCore, "_load_domains")
    @patch.object(BaseCore, "_load_entities")
    @patch('HomeAssistantPlugin.actions.cores.base_core.base_core.migrate_settings')
    def test_on_ready_success(self, migrate_settings_mock, load_entities_mock, load_domains_mock,
                              populate_config_ui_mock, refresh_mock, _, __):
        track_entity = True

        settings_implementation = Mock()
        settings_implementation.return_value = settings_implementation
        settings_implementation.get_entity.return_value = "entity"

        instance = BaseCore(settings_implementation, track_entity)
        instance.on_ready()

        migrate_settings_mock.assert_called_once_with(instance)
        instance.plugin_base.backend.add_action_ready_callback.assert_called_once_with(instance._on_backend_ready)
        settings_implementation.get_entity.assert_called_once()
        instance.plugin_base.backend.add_tracked_entity.assert_called_once_with("entity", instance.refresh)
        refresh_mock.assert_called_once()
        load_entities_mock.assert_not_called()
        load_domains_mock.assert_not_called()
        populate_config_ui_mock.assert_not_called()

    @patch.object(BaseCore, "create_ui_elements")
    @patch.object(BaseCore, "_create_event_assigner")
    @patch.object(BaseCore, "refresh")
    @patch.object(BaseCore, "_populate_config_ui")
    @patch('HomeAssistantPlugin.actions.cores.base_core.base_core.migrate_settings')
    def test_on_ready_not_connected_skips_tracking(self, migrate_settings_mock, populate_config_ui_mock,
                                                    refresh_mock, _, __):
        settings_implementation = Mock()
        settings_implementation.return_value = settings_implementation
        settings_implementation.get_entity.return_value = "entity"

        instance = BaseCore(settings_implementation, track_entity=True)
        instance.plugin_base.backend.is_connected.return_value = False
        instance.on_ready()

        instance.plugin_base.backend.add_action_ready_callback.assert_called_once_with(instance._on_backend_ready)
        instance.plugin_base.backend.add_tracked_entity.assert_not_called()
        refresh_mock.assert_called_once()


class TestBaseCoreOnBackendReady(unittest.TestCase):
    """_on_backend_ready is invoked by the backend, which marshals it onto the
    GTK main thread - so it may populate config-UI widgets."""

    @patch.object(BaseCore, "create_ui_elements")
    @patch.object(BaseCore, "_create_event_assigner")
    @patch.object(BaseCore, "refresh")
    @patch.object(BaseCore, "_populate_config_ui")
    def test_on_backend_ready_connected(self, populate_config_ui_mock, refresh_mock, _, __):
        settings_mock = Mock()
        settings_mock.get_entity.return_value = "entity"

        instance = BaseCore(Mock(), track_entity=True)
        instance.settings = settings_mock
        instance.initialized = True
        instance._config_ui_created = True
        instance.plugin_base.backend.is_connected.return_value = True

        instance._on_backend_ready()

        instance.plugin_base.backend.add_tracked_entity.assert_called_once_with("entity", instance.refresh)
        populate_config_ui_mock.assert_called_once()
        refresh_mock.assert_called_once()

    @patch.object(BaseCore, "create_ui_elements")
    @patch.object(BaseCore, "_create_event_assigner")
    @patch.object(BaseCore, "refresh")
    @patch.object(BaseCore, "_populate_config_ui")
    def test_on_backend_ready_disconnected(self, populate_config_ui_mock, refresh_mock, _, __):
        settings_mock = Mock()
        settings_mock.get_entity.return_value = "entity"

        instance = BaseCore(Mock(), track_entity=True)
        instance.settings = settings_mock
        instance.initialized = True
        instance._config_ui_created = True
        instance.plugin_base.backend.is_connected.return_value = False

        instance._on_backend_ready()

        instance.plugin_base.backend.add_tracked_entity.assert_not_called()
        populate_config_ui_mock.assert_called_once()
        refresh_mock.assert_not_called()
