"""The module for the Home Assistant action that is loaded in StreamController."""

import threading

import gi
from HomeAssistantPlugin.actions import const
from HomeAssistantPlugin.actions.cores.base_core.migrate import migrate_settings

from GtkHelper.GenerativeUI.ComboRow import ComboRow
from src.backend.PluginManager.ActionCore import ActionCore

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk


def set_substring_search(combo_row: ComboRow) -> None:
    """Enable substring search mode on a ComboRow if supported by the installed libadwaita version."""
    try:
        widget = combo_row.widget
        if hasattr(widget, "set_search_match_mode"):
            widget.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
    except AttributeError:
        pass


def requires_initialization(func):
    def wrapper(self, *args, **kwargs):
        if not getattr(self, 'initialized', False):
            return None
        return func(self, *args, **kwargs)

    return wrapper


class BaseCore(ActionCore):
    """Action core for all Home Assistant Actions."""

    def __init__(self, settings_implementation, track_entity: bool, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = None
        self.settings_implementation = settings_implementation
        self.initialized = False
        self.lm = self.plugin_base.locale_manager
        self.has_configuration = True
        self.track_entity = track_entity
        self.domain_combo = None
        self.entity_combo = None
        self._last_loaded_domains: list | None = None
        self._last_loaded_entities: list | None = None
        self._config_ui_created = False
        self._config_ui_sync_queued = False
        self._disposed = False
        self._entity_updated_callback = self._on_entity_updated
        self._ui_lock = threading.RLock()
        self._lifecycle_generation = 0
        self._ready_lock = threading.Lock()
        self._last_registered_entity = None
        self._create_event_assigner()

    def on_ready(self) -> None:
        """Set up the action without touching configuration widgets.

        StreamController may call this more than once and from a worker thread.
        Follow the OSPlugin lifecycle: initialize runtime state here and leave
        configuration-row construction to ``get_config_rows``.
        """
        with self._ready_lock:
            if self._disposed:
                return
            first_ready = not self.initialized
            if first_ready:
                migrate_settings(self)
                self.settings = self.settings_implementation(self)
                self.initialized = True
                self.plugin_base.backend.add_action_ready_callback(self._on_backend_ready)

        if self._disposed:
            return

        if self.plugin_base.backend.is_connected():
            self._track_entity()

        if first_ready:
            self.refresh()

    def _track_entity(self) -> None:
        """Subscribe to updates for the configured entity, if any."""
        entity = self.settings.get_entity()
        if entity and self.track_entity and entity != self._last_registered_entity:
            self.plugin_base.backend.add_tracked_entity(entity, self.refresh)
            self._last_registered_entity = entity

    def _on_entity_updated(self, state: dict = None) -> None:
        """Handle backend entity updates without touching GTK off-thread."""
        if self._disposed:
            return
        self.refresh(state)
        self._queue_config_ui_sync()

    def ensure_config_ui(self) -> None:
        """Create configuration widgets once, from the GTK configuration path."""
        lock = getattr(self, "_ui_lock", None)
        if lock is None:
            if getattr(self, "_config_ui_created", False):
                return
            if getattr(self, "domain_combo", None) is not None and getattr(self, "entity_combo", None) is not None:
                self._config_ui_created = True
                return
            if threading.current_thread() is not threading.main_thread():
                raise RuntimeError("Configuration widgets must be created on the GTK main thread")
            self.create_ui_elements()
            self._config_ui_created = True
            return

        with lock:
            if getattr(self, "_config_ui_created", False):
                return
            if getattr(self, "domain_combo", None) is not None and getattr(self, "entity_combo", None) is not None:
                self._config_ui_created = True
                return
            if threading.current_thread() is not threading.main_thread():
                raise RuntimeError("Configuration widgets must be created on the GTK main thread")

            self.create_ui_elements()
            self._config_ui_created = True

    def _on_backend_ready(self) -> None:
        """Handle Home Assistant (re)connect/disconnect.

        Invoked by the backend, which marshals it onto the GTK main thread via
        ``GLib.idle_add`` - so it is safe to populate config-UI widgets here.
        """
        if self._disposed or not self.initialized:
            return
        if self.plugin_base.backend.is_connected():
            self._track_entity()
            if self._config_ui_created:
                self._populate_config_ui()
            self.refresh()
        elif self._config_ui_created:
            self._populate_config_ui()

    @requires_initialization
    def on_remove(self) -> None:
        """Clean up after action was removed."""
        self._disposed = True
        self._lifecycle_generation += 1
        self.initialized = False
        self.plugin_base.backend.remove_action_ready_callback(self._on_backend_ready)

        if self.track_entity:
            self.plugin_base.backend.remove_tracked_entity(
                self.settings.get_entity(),
                self.refresh
            )
            self._last_registered_entity = None
        if self._config_ui_created:
            self._clear_config_ui()

    def on_removed_from_cache(self) -> None:
        """Invalidate plugin callbacks when StreamController evicts the action."""
        if self.initialized:
            self.on_remove()
        super().on_removed_from_cache()

    def _clear_config_ui(self) -> None:
        """Clear owned configuration rows during teardown."""
        customization_expander = getattr(self, "customization_expander", None)
        if customization_expander is not None:
            customization_expander.clear_rows()

    def get_config_rows(self) -> list:
        """Get the rows to be displayed in the UI."""
        raise NotImplementedError("Must be implemented by subclasses.")

    def create_ui_elements(self) -> None:
        """Get all entity rows."""
        self.domain_combo: ComboRow = ComboRow(
            self, const.SETTING_ENTITY_DOMAIN, const.EMPTY_STRING, [],
            const.LABEL_ENTITY_DOMAIN, enable_search=True,
            on_change=self.on_change_domain, can_reset=False,
            complex_var_name=True
        )
        set_substring_search(self.domain_combo)

        self.entity_combo: ComboRow = ComboRow(
            self, const.SETTING_ENTITY_ENTITY, const.EMPTY_STRING, [],
            const.LABEL_ENTITY_ENTITY, enable_search=True,
            on_change=self.on_change_entity, can_reset=False,
            complex_var_name=True
        )
        set_substring_search(self.entity_combo)

    def _queue_config_ui_sync(self) -> None:
        """Schedule a single configuration refresh on the GTK main loop."""
        if self._disposed or not getattr(self, "_config_ui_created", False) or self._config_ui_sync_queued:
            return
        self._config_ui_sync_queued = True

        def sync():
            self._config_ui_sync_queued = False
            if not self._disposed and self._config_ui_created:
                self._populate_config_ui()
            return GLib.SOURCE_REMOVE

        if threading.current_thread() is threading.main_thread():
            sync()
        else:
            GLib.idle_add(sync)

    @requires_initialization
    def _reload(self, *_):
        """Reload the action.

        Invoked from config-editor ``on_change`` callbacks (main thread).
        """
        self.set_enabled_disabled()
        self.refresh()

    @requires_initialization
    def _populate_config_ui(self) -> None:
        """Populate configuration widgets from cache-safe backend data."""
        if not self._config_ui_created or self._disposed:
            return
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Configuration widgets must be updated on the GTK main thread")
        self._load_domains()
        self._load_entities()
        self._populate_extra_config()
        self.set_enabled_disabled()

    def _populate_extra_config(self) -> None:
        """Hook for subclasses to populate their own config combos before
        ``set_enabled_disabled`` runs. Runs on the GTK main thread."""
        pass

    @requires_initialization
    def on_change_domain(self, _, domain, old_domain):
        """Execute when the domain is changed."""
        domain = str(domain) if domain is not None else None
        old_domain = str(old_domain) if old_domain is not None else None

        if old_domain != domain:
            entity = self.settings.get_entity()
            if entity and self.track_entity:
                self.plugin_base.backend.remove_tracked_entity(entity, self.refresh)
                self._last_registered_entity = None
            self.settings.reset(domain)
            # save entities from the combo to a temporary variable to keep them alive while we clear the combo
            _temp_keep_alive = [self.entity_combo.get_item_at(i) for i in range(self.entity_combo.get_item_amount())]
            self.entity_combo.remove_all_items()
            # now the entities can be removed
            del _temp_keep_alive
            self._last_loaded_entities = None

        if domain:
            self._load_entities()

        self.set_enabled_disabled()
        self._queue_config_ui_sync()

    @requires_initialization
    def on_change_entity(self, _, entity, old_entity):
        """Execute when the entity is changed."""
        entity = str(entity) if entity is not None else None
        old_entity = str(old_entity) if old_entity is not None else None

        if old_entity and self.track_entity:
            self.plugin_base.backend.remove_tracked_entity(old_entity, self.refresh)
            self._last_registered_entity = None

        if entity and self.track_entity:
            self.plugin_base.backend.add_tracked_entity(entity, self.refresh)
            self._last_registered_entity = entity

        self.refresh()
        self.set_enabled_disabled()
        self._queue_config_ui_sync()

    def on_update(self) -> None:
        """Render output on StreamController update without reinitializing."""
        if self._disposed:
            return
        self.refresh()

    @requires_initialization
    def refresh(self, state: dict = None) -> None:
        """
        Executed when an entity is updated to reflect the changes on the key.
        This does not need to do anything by default, but can be overridden by subclasses.
        :param state: The state of the entity, if available.
        """
        pass

    def _create_event_assigner(self) -> None:
        """
        Create the events that can be triggered in this action.
        This does not need to do anything by default, but can be overridden by subclasses.
        """
        pass

    @requires_initialization
    def _load_domains(self) -> None:
        """Load domains from Home Assistant."""
        domain = self.settings.get_domain()
        domains = self._get_domains()
        if domain is not None and domain not in domains:
            domains.append(domain)
        domains = [d for d in domains if d is not None]
        domains.sort()
        old_domains = self._last_loaded_domains
        self._last_loaded_domains = list(domains)
        if domains != old_domains:
            self.domain_combo.populate(domains, domain, trigger_callback=False)

    @requires_initialization
    def _get_cached_entities(self, domain: str) -> list[str]:
        """Read entities without forcing a network request from the UI."""
        backend = self.plugin_base.backend
        cached_getter = getattr(backend, "get_cached_entities", None)
        if callable(cached_getter) and not hasattr(cached_getter, "return_value"):
            return cached_getter(domain)
        return backend.get_entities(domain)

    def _load_entities(self) -> None:
        """Load entities from the local Home Assistant cache."""
        entity = self.settings.get_entity()
        entities = self._get_cached_entities(str(self.domain_combo.get_selected_item()))
        if entity is not None and entity not in entities:
            entities.append(entity)
        entities = [e for e in entities if e is not None]
        entities.sort()
        old_entities = self._last_loaded_entities
        self._last_loaded_entities = list(entities)
        if entities != old_entities:
            self.entity_combo.populate(entities, entity, trigger_callback=False)

    @requires_initialization
    def set_enabled_disabled(self) -> None:
        """Set the active/inactive state for all rows."""
        domain = self.settings.get_domain()
        is_domain_set = bool(domain)
        self.entity_combo.set_sensitive(is_domain_set)

    def _get_domains(self) -> list[str]:
        """Get the domains available in Home Assistant."""
        raise NotImplementedError("Must be implemented by subclasses.")

    def get_generative_ui(self):
        return []
