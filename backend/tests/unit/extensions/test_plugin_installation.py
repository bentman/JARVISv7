from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.actions.boundaries import ActionCancelledError, ActionOperation, ExecutionBoundary
from backend.app.extensions.discovery import parse_definition_manifest
from backend.app.extensions.plugins import PluginInstaller
from backend.tests.symlink_helpers import symlink_or_skip


def _operation() -> ActionOperation:
    return ActionOperation(
        "session-1", "turn-1", "proposal-1", "plugin-install",
        ExecutionBoundary(("data",), 2_000, True, 10_000),
    )


def _manifest() -> object:
    return parse_definition_manifest(
        "plugin",
        """
id: release-tools
name: Release tools
version: '1'
definition:
  source: release-tools-bundle
  extensions:
    - family: mcp
      id: release-notes
      path: mcp/release-notes.yaml
""",
        "config/extensions/plugins/release-tools.yaml",
        "config/extensions",
        "application",
    )


def _bundle(config: Path) -> Path:
    bundle = config / "extensions" / "plugins" / "release-tools-bundle" / "mcp"
    bundle.mkdir(parents=True)
    (bundle / "release-notes.yaml").write_text("id: release-notes\nname: Release notes\nversion: '1'\ndefinition:\n  transport: streamable_http\n  url: https://example.invalid/mcp\n", encoding="utf-8")
    return bundle.parent


def test_installs_a_local_bundle_atomically_and_reports_hash_evidence(tmp_path: Path) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    _bundle(config)
    installer = PluginInstaller(config, data)

    result = installer.install(_manifest(), _operation())

    destination = data / "extensions" / "plugins" / "release-tools"
    assert result["status"] == "installed"
    assert len(result["bundle_sha256"]) == 64
    assert (destination / "mcp" / "release-notes.yaml").is_file()
    children = installer.installed_definitions()
    assert len(children) == 1
    child = children[0]
    assert (child.plugin_id, child.family, child.local_id) == (
        "release-tools", "mcp", "release-notes"
    )


def test_same_bundle_is_idempotent_but_a_changed_destination_is_rejected(tmp_path: Path) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    _bundle(config)
    installer = PluginInstaller(config, data)

    assert installer.install(_manifest(), _operation())["status"] == "installed"
    assert installer.install(_manifest(), _operation())["status"] == "already_installed"
    (data / "extensions" / "plugins" / "release-tools" / "mcp" / "release-notes.yaml").write_text(
        "changed", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="destination collision"):
        installer.install(_manifest(), _operation())


@pytest.mark.parametrize("source", ["../escape", "/tmp/escape"])
def test_refuses_source_paths_outside_the_plugin_root(tmp_path: Path, source: str) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    installer = PluginInstaller(config, data)
    manifest = parse_definition_manifest(
        "plugin",
        f"""id: release-tools\nname: Release tools\nversion: '1'\ndefinition:\n  source: {source}\n  extensions: []\n""",
        "config/extensions/plugins/release-tools.yaml", "config/extensions", "application",
    )

    with pytest.raises(ValueError, match="stay inside the bundle"):
        installer.install(manifest, _operation())


def test_refuses_a_symlink_in_the_bundle(tmp_path: Path) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    bundle = _bundle(config)
    outside = tmp_path / "outside.yaml"
    outside.write_text("outside", encoding="utf-8")
    symlink_or_skip(outside, bundle / "mcp" / "escape.yaml")

    with pytest.raises(ValueError, match="contains a symlink"):
        PluginInstaller(config, data).install(_manifest(), _operation())


def test_cancelled_install_removes_its_temporary_directory(tmp_path: Path) -> None:
    config, data = tmp_path / "config", tmp_path / "data"
    _bundle(config)
    operation = _operation()
    operation.cancel.set()

    with pytest.raises(ActionCancelledError, match="action cancelled"):
        PluginInstaller(config, data).install(_manifest(), operation)

    assert not (data / "extensions" / "plugins" / "release-tools").exists()
    root = data / "extensions" / "plugins"
    assert not root.exists() or not list(root.glob(".release-tools.install-*"))
