"""Shared pytest fixtures for Lightbox tests."""

import pytest


@pytest.fixture
def temp_lightbox_dir(tmp_path, monkeypatch):
    """Set up a temporary Lightbox directory."""
    monkeypatch.setenv("LIGHTBOX_DIR", str(tmp_path))
    return tmp_path
