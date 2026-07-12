"""Tests for comment-preserving atomic YAML text updates."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.utils import yaml_text


def test_patch_yaml_values_keeps_target_when_atomic_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.yaml"
    original = "enabled: false # keep\n"
    path.write_text(original, encoding="utf-8")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(yaml_text.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        yaml_text.patch_yaml_values(path, {"enabled": True})

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".config.yaml.*.tmp")) == []
