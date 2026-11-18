"""GTK3 control panel for Ensemble."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .config import (  # noqa: E402
    Config,
    ConfigError,
    PROVIDER_ID_RE,
    Provider,
    RoleAssignment,
    config_path,
    default_config,
    load_config,
    save_config,
)
from .discovery import DiscoveryError, discover_provider  # noqa: E402
from .launch import (  # noqa: E402
    LaunchError,
    build_launch_plan,
    redacted_preview,
    terminal_command,
)
from .opencode_config import opencode_config_path, write_opencode_config  # noqa: E402
from .presets import PRESETS, provider_from_preset  # noqa: E402
from .secrets import (  # noqa: E402
    SecretError,
    keyring_available,
    resolve_secret,
    set_secret,
)
from .skill import SkillError, install_skill  # noqa: E402

ROLE_ORDER = ("orchestrator", "reviewer", "test_runner")
ROLE_TITLES = {
    "orchestrator": "Orchestrator",
    "reviewer": "Reviewer",
    "test_runner": "Test runner",
}
ROLE_DESCRIPTIONS = {
    "orchestrator": "Drives Claude Code. Requires an Anthropic-compatible provider.",
    "reviewer": "Read-only review through opencode.",
    "test_runner": "Read-only test planning through opencode.",
}


def _dim(label: Gtk.Label) -> Gtk.Label:
    label.get_style_context().add_class("dim-label")
    label.set_xalign(0)
    return label


class ModelChooserDialog(Gtk.Dialog):
    def __init__(self, parent, ids: list[str], selected: set[str]):
        super().__init__(
            title="Select models",
            transient_for=parent,
            modal=True,
        )
        self.set_default_size(560, 560)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Use selected", Gtk.ResponseType.OK)
        self.checks: list[tuple[str, Gtk.CheckButton, Gtk.ListBoxRow]] = []

        box = self.get_content_area()
        box.set_spacing(6)
        box.set_border_width(10)
        self.search = Gtk.SearchEntry(placeholder_text="Filter models")
        self.search.connect("changed", self._on_filter)
        box.pack_start(self.search, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        for model_id in ids:
            check = Gtk.CheckButton(label=model_id)
            check.set_active(model_id in selected)
            row = Gtk.ListBoxRow()
            row.add(check)
            listbox.add(row)
            self.checks.append((model_id, check, row))
        scroller.add(listbox)
        box.pack_start(scroller, True, True, 0)
        self.show_all()

    def _on_filter(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().lower()
        for model_id, _check, row in self.checks:
            row.set_visible(query in model_id.lower())

    def selected(self) -> list[str]:
        return [model_id for model_id, check, _row in self.checks if check.get_active()]


class ProviderDialog(Gtk.Dialog):
    def __init__(self, parent, provider: Provider | None, config: Config):
        title = "Edit provider" if provider else "Add provider"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.provider = provider
        self.config = config
        self.models_url = provider.models_url if provider else ""
        self.verify_url = provider.verify_url if provider else ""
        self.set_default_size(600, 560)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.save_button = self.add_button("Save", Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8, margin=12)
        self.get_content_area().add(grid)
        self.id_entry = Gtk.Entry()
        self.label_entry = Gtk.Entry()
        self.protocol_combo = Gtk.ComboBoxText()
        for protocol in ("anthropic", "openai"):
            self.protocol_combo.append(protocol, protocol)
        self.kind_combo = Gtk.ComboBoxText()
        self.kind_combo.append("custom", "Custom endpoint")
        self.kind_combo.append("builtin", "Built-in (opencode native)")
        self.auth_combo = Gtk.ComboBoxText()
        self.auth_combo.append("bearer", "Bearer token")
        self.auth_combo.append("x-api-key", "x-api-key header")
        self.base_entry = Gtk.Entry()
        self.env_entry = Gtk.Entry()
        self.models_entry = Gtk.Entry()
        self.preset_combo = Gtk.ComboBoxText()
        self.preset_combo.append("custom", "Custom provider")
        for preset in PRESETS.values():
            self.preset_combo.append(preset.id, f"{preset.label} preset")
        self.preset_combo.set_active_id("custom")
        self.preset_combo.connect("changed", self._on_preset_changed)
        self.key_entry = Gtk.Entry()
        self.key_entry.set_visibility(False)
        self.key_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.key_entry.set_placeholder_text("Leave blank to keep the stored key")
        self.file_check = Gtk.CheckButton(
            label=(
                "Store in a protected 0600 file if the keyring is unavailable"
            )
        )
        self.key_status = _dim(Gtk.Label())
        self.feedback = Gtk.Label(xalign=0)
        self.feedback.set_line_wrap(True)

        models_box = Gtk.Box(spacing=6)
        models_box.pack_start(self.models_entry, True, True, 0)
        self.fetch_button = Gtk.Button(label="Fetch models")
        self.fetch_button.connect("clicked", self._on_fetch)
        models_box.pack_start(self.fetch_button, False, False, 0)

        rows = []
        if provider is None:
            rows.append(("Preset", self.preset_combo))
        rows.extend(
            [
                ("ID", self.id_entry),
                ("Label", self.label_entry),
                ("Protocol", self.protocol_combo),
                ("Provider type", self.kind_combo),
                ("Base URL", self.base_entry),
                ("API key env var", self.env_entry),
                ("Auth header", self.auth_combo),
                ("Models (comma-separated)", models_box),
                ("API key", self.key_entry),
                ("Key fallback", self.file_check),
                ("", self.key_status),
            ]
        )
        for index, (label, widget) in enumerate(rows):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, index, 1, 1)
            grid.attach(widget, 1, index, 1, 1)
        grid.attach(self.feedback, 0, len(rows), 2, 1)

        self._updating_env = False
        self._env_touched = False
        self.id_entry.connect("changed", self._on_id_changed)
        self.env_entry.connect("changed", self._on_env_edited)
        for widget in (
            self.id_entry,
            self.label_entry,
            self.protocol_combo,
            self.kind_combo,
            self.base_entry,
            self.env_entry,
            self.auth_combo,
            self.models_entry,
        ):
            widget.connect("changed", self._on_validate)

        if provider is not None:
            self.id_entry.set_text(provider.id)
            self.id_entry.set_sensitive(False)
            self.label_entry.set_text(provider.label)
            self.protocol_combo.set_active_id(provider.protocol)
            self.kind_combo.set_active_id(provider.kind)
            self.auth_combo.set_active_id(provider.auth_style)
            self.base_entry.set_text(provider.base_url)
            self.env_entry.set_text(provider.env_var)
            self.models_entry.set_text(", ".join(provider.models))
            secret, source = resolve_secret(provider)
            self.key_status.set_text(
                f"Key: {source if secret else 'missing'} "
                "(enter a new value to replace it)"
            )
        else:
            self.protocol_combo.set_active_id("openai")
            self.kind_combo.set_active_id("custom")
            self.auth_combo.set_active_id("bearer")
            self.key_status.set_text("Key: not stored")

        self._on_validate()
        self.show_all()

    def _on_id_changed(self, entry: Gtk.Entry) -> None:
        if self.provider is not None or self._env_touched:
            return
        raw = entry.get_text().strip().upper().replace("-", "_").replace(" ", "_")
        self._updating_env = True
        self.env_entry.set_text(f"{raw}_API_KEY" if raw else "")
        self._updating_env = False

    def _on_preset_changed(self, combo: Gtk.ComboBoxText) -> None:
        preset_id = combo.get_active_id()
        if preset_id in PRESETS:
            provider = provider_from_preset(preset_id)
            self._env_touched = True
            self.id_entry.set_text(provider.id)
            self.id_entry.set_sensitive(False)
            self.label_entry.set_text(provider.label)
            self.protocol_combo.set_active_id(provider.protocol)
            self.kind_combo.set_active_id(provider.kind)
            self.auth_combo.set_active_id(provider.auth_style)
            self.base_entry.set_text(provider.base_url)
            self.env_entry.set_text(provider.env_var)
            self.models_url = provider.models_url
            self.verify_url = provider.verify_url
            for widget in (
                self.protocol_combo,
                self.kind_combo,
                self.base_entry,
                self.env_entry,
                self.auth_combo,
            ):
                widget.set_sensitive(False)
            self.feedback.set_text(
                "Preset loaded. Enter an API key, then Fetch models."
            )
        else:
            self.id_entry.set_sensitive(True)
            self.models_url = ""
            self.verify_url = ""
            for widget in (
                self.protocol_combo,
                self.kind_combo,
                self.base_entry,
                self.env_entry,
                self.auth_combo,
            ):
                widget.set_sensitive(True)
            self.feedback.set_text(
                "Custom provider: set the endpoint and env var manually."
            )

    def _on_env_edited(self, _entry: Gtk.Entry) -> None:
        if not self._updating_env:
            self._env_touched = True

    def _on_validate(self, *_args) -> None:
        try:
            provider = self.get_provider()
        except Exception:
            self.save_button.set_sensitive(False)
            return
        valid = (
            bool(PROVIDER_ID_RE.match(provider.id))
            and bool(provider.label)
            and bool(provider.env_var)
            and (provider.kind == "builtin" or bool(provider.base_url))
        )
        self.save_button.set_sensitive(valid)
        if not valid:
            self.feedback.set_text(
                "ID, label, env var, and base URL (for custom providers) are required."
            )
        else:
            self.feedback.set_text("")

    def get_provider(self) -> Provider:
        provider_id = self.id_entry.get_text().strip().lower()
        models = [
            model.strip()
            for model in self.models_entry.get_text().split(",")
            if model.strip()
        ]
        return Provider(
            id=provider_id,
            label=self.label_entry.get_text().strip() or provider_id,
            protocol=self.protocol_combo.get_active_id() or "openai",
            env_var=self.env_entry.get_text().strip(),
            base_url=self.base_entry.get_text().strip(),
            kind=self.kind_combo.get_active_id() or "custom",
            auth_style=self.auth_combo.get_active_id() or "bearer",
            models_url=self.models_url,
            verify_url=self.verify_url,
            models=models,
        )

    def key_value(self) -> str:
        return self.key_entry.get_text().strip()

    def allow_file_value(self) -> bool:
        return self.file_check.get_active()

    def _current_models(self) -> list[str]:
        return [
            model.strip()
            for model in self.models_entry.get_text().split(",")
            if model.strip()
        ]

    def _on_fetch(self, _button: Gtk.Button) -> None:
        try:
            provider = self.get_provider()
        except Exception as exc:
            self.feedback.set_text(str(exc))
            return
        if not provider.base_url:
            self.feedback.set_text("Enter a base URL first.")
            return
        key = self.key_entry.get_text().strip()
        if not key and self.provider is not None:
            key, _source = resolve_secret(self.provider)
        if not key:
            self.feedback.set_text("Enter an API key first.")
            return
        self.fetch_button.set_sensitive(False)
        self.feedback.set_text("Fetching models…")

        def worker() -> None:
            try:
                ids = discover_provider(provider, key)
                GLib.idle_add(self._on_fetched, ids, None)
            except DiscoveryError as exc:
                GLib.idle_add(self._on_fetched, None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetched(self, ids, error):
        self.fetch_button.set_sensitive(True)
        if error:
            self.feedback.set_text(f"Fetch failed: {error}")
            return False
        current = self._current_models()
        dialog = ModelChooserDialog(self, ids, set(current))
        response = dialog.run()
        try:
            if response == Gtk.ResponseType.OK:
                selected = dialog.selected()
                merged = selected + [model for model in current if model not in ids]
                self.models_entry.set_text(", ".join(merged))
                self.feedback.set_text(
                    f"Fetched {len(ids)} models; {len(selected)} selected."
                )
        finally:
            dialog.destroy()
        return False


class ProvidersPage:
    def __init__(self, window: "MainWindow"):
        self.window = window
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.widget.set_border_width(12)

        toolbar = Gtk.Box(spacing=6)
        for label, handler in (
            ("Add provider", self.on_add),
            ("Edit", self.on_edit),
            ("Discover models", self.on_discover),
            ("Remove", self.on_remove),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", handler)
            toolbar.pack_start(button, False, False, 0)
        self.widget.pack_start(toolbar, False, False, 0)

        self.store = Gtk.ListStore(str, str, str, int, str)
        self.tree = Gtk.TreeView(model=self.store)
        for index, (title, width) in enumerate(
            (
                ("ID", 140),
                ("Label", 160),
                ("Protocol", 100),
                ("Models", 70),
                ("Key", 120),
            )
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_resizable(True)
            column.set_min_width(width)
            self.tree.append_column(column)
        self.tree.connect("row-activated", self.on_edit)
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.add(self.tree)
        self.widget.pack_start(scroller, True, True, 0)
        self.widget.pack_start(
            _dim(
                Gtk.Label(
                    label=(
                        "Keys live in the OS keyring. The Key column shows the "
                        "source, never the value."
                    )
                )
            ),
            False,
            False,
            0,
        )

    def refresh(self) -> None:
        self.store.clear()
        for provider_id in sorted(self.window.config.providers):
            provider = self.window.config.providers[provider_id]
            secret, source = resolve_secret(provider)
            self.store.append(
                [
                    provider_id,
                    provider.label,
                    provider.protocol,
                    len(provider.models),
                    source if secret else "missing",
                ]
            )

    def _selected_id(self) -> str | None:
        model, treeiter = self.tree.get_selection().get_selected()
        if treeiter is None:
            return None
        return model[treeiter][0]

    def _after_change(self) -> None:
        self.refresh()
        self.window.roles_page.refresh()
        self.window.launch_page.refresh_preview()
        self.window.mark_dirty()

    def on_add(self, _button=None) -> None:
        dialog = ProviderDialog(self.window, None, self.window.config)
        response = dialog.run()
        try:
            if response != Gtk.ResponseType.OK:
                return
            provider = dialog.get_provider()
            if provider.id in self.window.config.providers:
                self.window.error("Provider already exists", provider.id)
                return
            key = dialog.key_value()
            if key:
                try:
                    set_secret(
                        provider,
                        key,
                        allow_file=dialog.allow_file_value(),
                    )
                except SecretError as exc:
                    self.window.error("Could not store the key", str(exc))
                    return
            self.window.config.providers[provider.id] = provider
            self._after_change()
        finally:
            dialog.destroy()

    def on_edit(self, _tree=None, _path=None, _column=None) -> None:
        provider_id = self._selected_id()
        if provider_id is None:
            return
        provider = self.window.config.providers[provider_id]
        dialog = ProviderDialog(self.window, provider, self.window.config)
        response = dialog.run()
        try:
            if response != Gtk.ResponseType.OK:
                return
            updated = dialog.get_provider()
            key = dialog.key_value()
            if key:
                try:
                    set_secret(
                        updated,
                        key,
                        allow_file=dialog.allow_file_value(),
                    )
                except SecretError as exc:
                    self.window.error("Could not store the key", str(exc))
                    return
            self.window.config.providers[updated.id] = updated
            self._after_change()
        finally:
            dialog.destroy()

    def on_discover(self, _button=None) -> None:
        provider_id = self._selected_id()
        if provider_id is None:
            return
        provider = self.window.config.providers[provider_id]
        secret, _source = resolve_secret(provider)
        if not secret:
            self.window.error(
                "No API key",
                f"Run 'ensemble key set {provider_id}' or export "
                f"${provider.env_var}.",
            )
            return
        self.window.set_status(f"Discovering models for {provider_id}…")

        def worker() -> None:
            try:
                models = discover_provider(provider, secret)
                GLib.idle_add(
                    self._on_models_discovered, provider_id, models, None
                )
            except DiscoveryError as exc:
                GLib.idle_add(
                    self._on_models_discovered, provider_id, None, str(exc)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_models_discovered(self, provider_id, models, error):
        if error:
            self.window.error("Model discovery failed", error)
            return False
        provider = self.window.config.providers.get(provider_id)
        if provider is None:
            return False
        provider.models = models
        self.window.mark_dirty()
        self.refresh()
        self.window.roles_page.refresh()
        self.window.launch_page.refresh_preview()
        self.window.set_status(
            f"{provider_id}: {len(models)} models discovered (unsaved)"
        )
        return False

    def on_remove(self, _button=None) -> None:
        provider_id = self._selected_id()
        if provider_id is None:
            return
        used_by = [
            role
            for role, assignment in self.window.config.roles.items()
            if assignment.provider == provider_id
        ]
        if used_by:
            self.window.error(
                "Provider is in use",
                f"{provider_id} is assigned to: {', '.join(used_by)}.",
            )
            return
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove provider {provider_id}?",
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            del self.window.config.providers[provider_id]
            self._after_change()


class RolesPage:
    def __init__(self, window: "MainWindow"):
        self.window = window
        self._loading = False
        self.rows: dict[str, dict] = {}
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.widget.set_border_width(12)

        for role in ROLE_ORDER:
            frame = Gtk.Frame(label=ROLE_TITLES[role])
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            inner.set_border_width(10)
            inner.pack_start(_dim(Gtk.Label(label=ROLE_DESCRIPTIONS[role])), False, False, 0)
            grid = Gtk.Grid(column_spacing=10, row_spacing=6)

            provider_combo = Gtk.ComboBoxText()
            provider_combo.connect("changed", self._on_provider_changed, role)
            grid.attach(Gtk.Label(label="Provider", xalign=0), 0, 0, 1, 1)
            grid.attach(provider_combo, 1, 0, 1, 1)

            model_store = Gtk.ListStore(str)
            model_combo = Gtk.ComboBox.new_with_entry()
            model_combo.set_model(model_store)
            model_combo.set_entry_text_column(0)
            model_combo.get_child().connect(
                "changed", self._on_model_changed, role
            )
            grid.attach(Gtk.Label(label="Model", xalign=0), 0, 1, 1, 1)
            grid.attach(model_combo, 1, 1, 1, 1)

            small_entry = None
            if role == "orchestrator":
                small_entry = Gtk.Entry()
                small_entry.connect("changed", self._on_model_changed, role)
                grid.attach(
                    Gtk.Label(label="Fast/background model", xalign=0),
                    0,
                    2,
                    1,
                    1,
                )
                grid.attach(small_entry, 1, 2, 1, 1)

            inner.pack_start(grid, False, False, 0)
            frame.add(inner)
            self.widget.pack_start(frame, False, False, 0)
            self.rows[role] = {
                "provider": provider_combo,
                "model": model_combo,
                "model_store": model_store,
                "small": small_entry,
            }

    def refresh(self) -> None:
        self._loading = True
        try:
            for role in ROLE_ORDER:
                row = self.rows[role]
                assignment = self.window.config.roles[role]
                combo = row["provider"]
                combo.remove_all()
                for provider_id in sorted(self.window.config.providers):
                    provider = self.window.config.providers[provider_id]
                    if role == "orchestrator" and provider.protocol != "anthropic":
                        continue
                    combo.append(
                        provider_id,
                        f"{provider.label} ({provider_id}, {provider.protocol})",
                    )
                combo.set_active_id(assignment.provider)
                self._populate_models(role)
                row["model"].get_child().set_text(assignment.model)
                if row["small"] is not None:
                    row["small"].set_text(assignment.small_model or "")
        finally:
            self._loading = False

    def _populate_models(self, role: str) -> None:
        row = self.rows[role]
        provider_id = row["provider"].get_active_id()
        store = row["model_store"]
        store.clear()
        if provider_id and provider_id in self.window.config.providers:
            for model in self.window.config.providers[provider_id].models:
                store.append([model])

    def _on_provider_changed(self, combo: Gtk.ComboBoxText, role: str) -> None:
        if self._loading:
            return
        self._populate_models(role)
        provider_id = combo.get_active_id()
        if provider_id:
            models = self.window.config.providers[provider_id].models
            entry = self.rows[role]["model"].get_child()
            if models and not entry.get_text().strip():
                entry.set_text(models[0])
        self.window.mark_dirty()
        self.window.launch_page.refresh_preview()

    def _on_model_changed(self, _entry, role: str) -> None:
        if self._loading:
            return
        self.window.mark_dirty()
        self.window.launch_page.refresh_preview()

    def save_to_config(self) -> None:
        for role in ROLE_ORDER:
            row = self.rows[role]
            provider_id = row["provider"].get_active_id()
            if not provider_id:
                raise ConfigError(f"Choose a provider for the {role} role")
            model = row["model"].get_child().get_text().strip()
            if not model:
                raise ConfigError(f"Choose a model for the {role} role")
            small = None
            if row["small"] is not None:
                small = row["small"].get_text().strip() or None
            self.window.config.roles[role] = RoleAssignment(
                provider=provider_id, model=model, small_model=small
            )
        self.window.config.validate()


class LaunchPage:
    def __init__(self, window: "MainWindow"):
        self.window = window
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.widget.set_border_width(12)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.repo_button = Gtk.FileChooserButton(
            title="Repository", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.repo_button.connect("selection-changed", self._on_change)
        self.rounds_spin = Gtk.SpinButton.new_with_range(1, 3, 1)
        self.rounds_spin.connect("value-changed", self._on_change)
        self.budget_spin = Gtk.SpinButton.new_with_range(0, 10, 0.1)
        self.budget_spin.set_digits(2)
        self.budget_spin.connect("value-changed", self._on_change)

        grid.attach(Gtk.Label(label="Repository", xalign=0), 0, 0, 1, 1)
        grid.attach(self.repo_button, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Rounds", xalign=0), 0, 1, 1, 1)
        grid.attach(self.rounds_spin, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Budget (USD)", xalign=0), 0, 2, 1, 1)
        grid.attach(self.budget_spin, 1, 2, 1, 1)
        self.widget.pack_start(grid, False, False, 0)

        self.preview = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
        )
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.add(self.preview)
        self.widget.pack_start(
            _dim(Gtk.Label(label="Environment preview (secrets redacted)")),
            False,
            False,
            0,
        )
        self.widget.pack_start(scroller, True, True, 0)

        buttons = Gtk.Box(spacing=6)
        apply_button = Gtk.Button(label="Save & Apply")
        apply_button.connect("clicked", lambda _b: self.window.apply_all())
        launch_button = Gtk.Button(label="Open Orchestrator")
        launch_button.connect("clicked", lambda _b: self.window.launch_orchestrator())
        buttons.pack_end(launch_button, False, False, 0)
        buttons.pack_end(apply_button, False, False, 0)
        self.widget.pack_start(buttons, False, False, 0)

    def refresh(self) -> None:
        self._loading = True
        try:
            repo = self.window.config.prefs.default_repo or os.getcwd()
            if Path(repo).is_dir():
                self.repo_button.set_filename(repo)
            self.rounds_spin.set_value(self.window.config.prefs.rounds)
            self.budget_spin.set_value(self.window.config.prefs.budget_usd)
        finally:
            self._loading = False
        self.refresh_preview()

    def _on_change(self, *_args) -> None:
        if getattr(self, "_loading", False):
            return
        self.window.mark_dirty()
        self.refresh_preview()

    def repo_path(self) -> Path | None:
        filename = self.repo_button.get_filename()
        return Path(filename).resolve() if filename else None

    def save_to_config(self) -> None:
        repo = self.repo_path()
        self.window.config.prefs.default_repo = str(repo) if repo else None
        self.window.config.prefs.rounds = int(self.rounds_spin.get_value())
        self.window.config.prefs.budget_usd = round(
            float(self.budget_spin.get_value()), 2
        )
        self.window.config.validate()

    def refresh_preview(self) -> None:
        try:
            plan = build_launch_plan(self.window.config)
            lines = redacted_preview(plan)
            lines.append(f"rounds: {int(self.rounds_spin.get_value())}")
            lines.append(f"budget: ${self.budget_spin.get_value():.2f}")
            text = "\n".join(lines)
        except (LaunchError, SecretError) as exc:
            text = f"Cannot launch: {exc}"
        self.preview.get_buffer().set_text(text)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application=None, initial_tab: str = "providers"):
        super().__init__(application=application, title="Ensemble")
        self.set_default_size(1000, 680)
        self._suppress_dirty = True
        self.config_path = config_path()
        self.config_error: str | None = None
        try:
            self.config = load_config()
        except ConfigError as exc:
            self.config = default_config()
            self.config_error = str(exc)
        self.dirty = False

        header = Gtk.HeaderBar(show_close_button=True)
        header.set_title("Ensemble")
        header.set_subtitle(str(self.config_path))
        apply_button = Gtk.Button(label="Save & Apply")
        apply_button.connect("clicked", lambda _b: self.apply_all())
        header.pack_end(apply_button)
        self.header = header
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        self.info_bar = Gtk.InfoBar()
        self.info_bar.set_no_show_all(True)
        self.info_bar.set_message_type(Gtk.MessageType.INFO)
        self.info_label = Gtk.Label(label="", xalign=0)
        self.info_label.set_line_wrap(True)
        self.info_bar.get_content_area().add(self.info_label)
        outer.pack_start(self.info_bar, False, False, 0)

        self.notebook = Gtk.Notebook()
        outer.pack_start(self.notebook, True, True, 0)
        self.providers_page = ProvidersPage(self)
        self.roles_page = RolesPage(self)
        self.launch_page = LaunchPage(self)
        for page, title in (
            (self.providers_page, "Providers"),
            (self.roles_page, "Roles"),
            (self.launch_page, "Launch"),
        ):
            self.notebook.append_page(page.widget, Gtk.Label(label=title))
        self.notebook.connect("switch-page", self._on_page_switched)

        self.status = Gtk.Label(label=f"Config: {self.config_path}", xalign=0)
        self.status.set_margin_start(12)
        self.status.set_margin_end(12)
        self.status.set_margin_bottom(6)
        outer.pack_end(self.status, False, False, 0)

        self.providers_page.refresh()
        self.roles_page.refresh()
        self.launch_page.refresh()
        messages = []
        if self.config_error:
            messages.append(
                f"{self.config_error} Defaults were loaded from the environment; "
                "click Save & Apply to write them."
            )
        if not keyring_available():
            messages.append(
                "OS keyring unavailable: keys can come from env vars, or from the "
                "opt-in protected file when storing a key."
            )
        if messages:
            self.show_info(" ".join(messages))
        self.show_all()
        pages = {"providers": 0, "roles": 1, "launch": 2}
        self.notebook.set_current_page(pages.get(initial_tab, 0))
        GLib.timeout_add(800, self._finish_startup)

    def _finish_startup(self):
        self._suppress_dirty = False
        self._mark_clean()
        return False

    def _on_page_switched(self, _notebook, _page, page_number: int) -> None:
        if page_number == 2:
            self.launch_page.refresh_preview()

    def show_info(self, text: str) -> None:
        self.info_label.set_text(text)
        self.info_bar.set_revealed(True)

    def error(self, title: str, detail: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def mark_dirty(self) -> None:
        if getattr(self, "_suppress_dirty", False):
            return
        self.dirty = True
        self.header.set_subtitle(f"{self.config_path}  •  unsaved")

    def _mark_clean(self) -> None:
        self.dirty = False
        self.header.set_subtitle(str(self.config_path))

    def apply_all(self) -> bool:
        try:
            self.roles_page.save_to_config()
            self.launch_page.save_to_config()
            save_config(self.config)
            write_opencode_config(self.config)
            try:
                install_skill(force=True)
            except SkillError as exc:
                self.error("Skill install failed", str(exc))
            self.providers_page.refresh()
            self.launch_page.refresh_preview()
            self._mark_clean()
            self.status.set_text(
                f"Saved {config_path()} and {opencode_config_path()}"
            )
            return True
        except (ConfigError, OSError) as exc:
            self.error("Could not save", str(exc))
            return False

    def launch_orchestrator(self) -> None:
        if not self.apply_all():
            return
        repo = self.launch_page.repo_path()
        if repo is None or not repo.is_dir():
            self.error("No repository", "Choose an existing repository folder.")
            return
        command = terminal_command(repo, self.config.prefs.terminal)
        try:
            subprocess.Popen(command, start_new_session=True)
        except OSError as exc:
            self.error("Could not launch terminal", str(exc))
            return
        self.status.set_text(f"Launched Claude Code in {repo}")


class EnsembleApplication(Gtk.Application):
    def __init__(self, initial_tab: str = "providers"):
        super().__init__(
            application_id="dev.ensemble.ControlPanel",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.initial_tab = initial_tab
        self.window = None

    def do_activate(self) -> None:
        if self.window is None:
            self.window = MainWindow(self, initial_tab=self.initial_tab)
        self.window.present()


def main(argv: list[str] | None = None, initial_tab: str = "providers") -> int:
    app = EnsembleApplication(initial_tab=initial_tab)
    return int(app.run(argv if argv is not None else sys.argv))


def smoke_test() -> int:
    app = EnsembleApplication()

    def quit_soon():
        for window in app.get_windows():
            window.destroy()
        app.quit()
        return False

    GLib.timeout_add(900, quit_soon)
    code = app.run(["ensemble-gui-smoke"])
    print("GUI smoke test completed")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
