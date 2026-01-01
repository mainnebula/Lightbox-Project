"""Tests for CLI commands."""

import json

import pytest
from click.testing import CliRunner

from lightbox.cli import main
from lightbox.core import Session
from lightbox.storage import get_events_file


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_session(temp_lightbox_dir):
    """Create a sample session with events."""
    session = Session("test_session")
    session.emit("send_email", {"to": "user@example.com"}, {"success": True})
    session.emit("read_file", {"path": "/tmp/data.txt"}, {"content": "Hello"})
    session.emit("api_call", {"url": "https://api.example.com"}, {"status": 200})
    return session


class TestListCommand:
    def test_empty_list(self, runner, temp_lightbox_dir):
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output

    def test_lists_sessions(self, runner, sample_session):
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "test_session" in result.output
        assert "3 events" in result.output


class TestShowCommand:
    def test_show_nonexistent(self, runner, temp_lightbox_dir):
        result = runner.invoke(main, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_show_events(self, runner, sample_session):
        result = runner.invoke(main, ["show", "test_session"])
        assert result.exit_code == 0
        assert "send_email" in result.output
        assert "read_file" in result.output
        assert "api_call" in result.output

    def test_show_raw(self, runner, sample_session):
        result = runner.invoke(main, ["show", "test_session", "--raw"])
        assert result.exit_code == 0

        # Each line should be valid JSON
        lines = result.output.strip().split("\n")
        assert len(lines) == 3

        for line in lines:
            data = json.loads(line)
            assert "tool" in data
            assert "hash" in data

    def test_show_verbose(self, runner, sample_session):
        result = runner.invoke(main, ["show", "test_session", "--verbose"])
        assert result.exit_code == 0
        assert "Input:" in result.output
        assert "Output:" in result.output


class TestVerifyCommand:
    def test_verify_nonexistent(self, runner, temp_lightbox_dir):
        result = runner.invoke(main, ["verify", "nonexistent"])
        assert result.exit_code == 4  # NOT_FOUND
        assert "not found" in result.output

    def test_verify_valid(self, runner, sample_session):
        result = runner.invoke(main, ["verify", "test_session"])
        assert result.exit_code == 0
        assert "verified" in result.output.lower() or "✓" in result.output
        assert "3 events" in result.output

    def test_verify_tampered(self, runner, sample_session):
        # Tamper with the events file
        events_file = get_events_file("test_session")
        lines = events_file.read_text().strip().split("\n")

        # Modify the second event
        event_data = json.loads(lines[1])
        event_data["input"]["path"] = "/hacked/path"
        lines[1] = json.dumps(event_data)

        events_file.write_text("\n".join(lines) + "\n")

        result = runner.invoke(main, ["verify", "test_session"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower() or "✗" in result.output


class TestReplayCommand:
    def test_replay_nonexistent(self, runner, temp_lightbox_dir):
        result = runner.invoke(main, ["replay", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_replay_fast(self, runner, sample_session):
        result = runner.invoke(main, ["replay", "test_session", "--fast"])
        assert result.exit_code == 0
        assert "REPLAY" in result.output
        assert "send_email" in result.output
        assert "COMPLETE" in result.output

    def test_replay_raw(self, runner, sample_session):
        result = runner.invoke(main, ["replay", "test_session", "--raw", "--fast"])
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        assert len(lines) == 3

        for line in lines:
            data = json.loads(line)
            assert "tool" in data


class TestVersionOption:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower() or "0.1.0" in result.output
