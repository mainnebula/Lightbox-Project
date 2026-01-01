"""Command-line interface for Lightbox.

Commands:
    lightbox list              List all recorded sessions
    lightbox show <session>    Show events in a session
    lightbox replay <session>  Animated playback of a session
    lightbox verify <session>  Verify hash chain integrity

EXIT CODES:
    0: Success (verify: valid)
    1: Failure (verify: tampered)
    2: Truncation detected (verify: partial write)
    3: Parse error (verify: invalid JSON)
    4: Not found

ENVIRONMENT:
    NO_COLOR: Disable colored output (any value)
    LIGHTBOX_DIR: Override default ~/.lightbox directory
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

import click

from lightbox import __version__
from lightbox.animation import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    MAGENTA,
    RED,
    YELLOW,
    colorize,
    replay_event,
    replay_footer,
    replay_header,
    spinner,
    startup_animation,
)
from lightbox.integrity import VerifyStatus, verify_session
from lightbox.models import Event
from lightbox.storage import (
    get_session_info,
    list_sessions,
    read_events,
    read_session_metadata,
    session_exists,
)


def _colors_enabled() -> bool:
    """Check if colors should be used."""
    # NO_COLOR standard: https://no-color.org/
    if os.environ.get("NO_COLOR"):
        return False
    # Also check if stdout is a TTY
    return sys.stdout.isatty()


def format_timestamp(iso_timestamp: str) -> str:
    """Format an ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_timestamp


def format_duration(start: str, end: str | None) -> str:
    """Format duration between two timestamps."""
    if not end:
        return "pending"
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        delta = end_dt - start_dt
        ms = int(delta.total_seconds() * 1000)
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        else:
            return f"{ms / 60000:.1f}m"
    except Exception:
        return "?"


def status_icon(status: str) -> str:
    """Get icon for event status."""
    icons = {
        "complete": colorize("✓", GREEN),
        "error": colorize("✗", RED),
        "pending": colorize("◌", YELLOW),
    }
    if not _colors_enabled():
        icons = {
            "complete": "[OK]",
            "error": "[ERR]",
            "pending": "[...]",
        }
    return icons.get(status, "?")


def format_event_line(event: Event, show_hash: bool = False) -> str:
    """Format a single event for display."""
    icon = status_icon(event.status)
    duration = format_duration(event.timestamp_start, event.timestamp_end)
    tool = colorize(event.tool, CYAN + BOLD)

    line = f"  {icon} {event.invocation_id} {tool} [{duration}]"

    if show_hash:
        short_hash = event.hash[:8]
        line += f" {colorize(short_hash, DIM)}"

    return line


def format_event_detail(event: Event) -> str:
    """Format event with input/output details."""
    lines = [format_event_line(event, show_hash=True)]

    # Input
    if event.input:
        input_json = json.dumps(event.input, indent=2)
        lines.append(colorize("    Input:", DIM))
        for input_line in input_json.split("\n"):
            lines.append(f"      {input_line}")

    # Canonical output (if available, show prominently)
    if event.canonical_output is not None:
        canonical_json = json.dumps(event.canonical_output, indent=2)
        lines.append(colorize("    Value:", GREEN))
        for canonical_line in canonical_json.split("\n"):
            lines.append(f"      {colorize(canonical_line, GREEN)}")

    # Raw output (show as secondary if canonical exists)
    if event.output:
        label = "    Raw output:" if event.canonical_output is not None else "    Output:"
        output_json = json.dumps(event.output, indent=2)
        lines.append(colorize(label, DIM))
        for output_line in output_json.split("\n"):
            lines.append(f"      {output_line}")

    # Error
    if event.error:
        error_json = json.dumps(event.error, indent=2)
        lines.append(colorize("    Error:", RED))
        for error_line in error_json.split("\n"):
            lines.append(f"      {colorize(error_line, RED)}")

    return "\n".join(lines)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.pass_context
def main(ctx):
    """Lightbox: Flight recorder for AI agents.

    Record, replay, and verify tool execution logs.
    """
    # Show startup animation if no subcommand
    if ctx.invoked_subcommand is None:
        startup_animation(version=__version__, duration=3.0)
        click.echo("Run 'lightbox --help' for available commands.\n")
        click.echo(colorize("Quick start:", BOLD))
        click.echo(f"  {colorize('lightbox list', CYAN)}              List all sessions")
        click.echo(f"  {colorize('lightbox show --last', CYAN)}       Show most recent session")
        click.echo(f"  {colorize('lightbox replay --last', CYAN)}     Replay most recent session")
        click.echo(f"  {colorize('lightbox verify <session>', CYAN)}  Verify integrity")
        click.echo()


@main.command("list")
def list_cmd():
    """List all recorded sessions."""
    sessions = list_sessions()

    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo(f"\n{colorize('Sessions', BOLD)} ({len(sessions)})\n")

    for session_id in sessions:
        info = get_session_info(session_id)
        if info:
            event_count = info["event_count"]
            first = format_timestamp(info["first_event"]) if info["first_event"] else "N/A"
            tools = ", ".join(info.get("tools_used", [])[:3])
            if len(info.get("tools_used", [])) > 3:
                tools += ", ..."

            click.echo(f"  {colorize(session_id, CYAN)}")
            click.echo(f"    {event_count} events | {first} | {tools}")
            click.echo()


def _resolve_session(session: str | None, use_last: bool) -> str | None:
    """Resolve session ID, handling --last flag."""
    if use_last:
        sessions = list_sessions()
        if not sessions:
            click.echo("No sessions found.", err=True)
            return None
        return sessions[0]
    return session


@main.command()
@click.argument("session", required=False)
@click.option("--last", "-l", is_flag=True, help="Use most recent session")
@click.option("--raw", is_flag=True, help="Output raw JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show input/output details")
@click.option("--inv", "invocation", help="Filter to specific invocation ID")
def show(session: str | None, last: bool, raw: bool, verbose: bool, invocation: str | None):
    """Show events in a session."""
    session = _resolve_session(session, last)
    if session is None:
        if not last:
            click.echo("Error: Missing argument 'SESSION'. Use --last for most recent.", err=True)
        sys.exit(4)

    if not session_exists(session):
        click.echo(f"Session '{session}' not found.", err=True)
        sys.exit(1)

    events = read_events(session)

    # Filter by invocation ID if specified
    if invocation:
        events = [e for e in events if e.invocation_id == invocation]
        if not events:
            click.echo(f"No events found for invocation '{invocation}'.", err=True)
            sys.exit(1)

    if raw:
        for event in events:
            click.echo(json.dumps(event.to_dict()))
        return

    if not events:
        click.echo("Session has no events.")
        return

    # Show session metadata
    meta = read_session_metadata(session)
    click.echo(f"\n{colorize('Session:', BOLD)} {session}")
    if meta:
        click.echo(
            f"{colorize('Schema:', DIM)} v{meta.schema_version} (lightbox {meta.lightbox_version})"
        )
    if invocation:
        click.echo(f"{colorize('Filter:', MAGENTA)} {invocation}")
    click.echo(f"{colorize('Events:', BOLD)} {len(events)}\n")

    for event in events:
        # When filtering by invocation, always show verbose details
        if verbose or invocation:
            click.echo(format_event_detail(event))
        else:
            click.echo(format_event_line(event, show_hash=True))
        click.echo()


@main.command()
@click.argument("session", required=False)
@click.option("--last", "-l", is_flag=True, help="Use most recent session")
@click.option("--fast", is_flag=True, help="Disable animations")
@click.option("--raw", is_flag=True, help="Output raw JSON")
def replay(session: str | None, last: bool, fast: bool, raw: bool):
    """Animated playback of a session.

    Replays events with timing delays and cassette tape animation.
    Use --fast to disable animations, --raw for JSON output.
    """
    session = _resolve_session(session, last)
    if session is None:
        if not last:
            click.echo("Error: Missing argument 'SESSION'. Use --last for most recent.", err=True)
        sys.exit(4)

    if not session_exists(session):
        click.echo(f"Session '{session}' not found.", err=True)
        sys.exit(1)

    events = read_events(session)

    if raw:
        for event in events:
            click.echo(json.dumps(event.to_dict()))
            if not fast:
                time.sleep(0.1)
        return

    if not events:
        click.echo("Session has no events.")
        return

    # Animated header with cassette
    if not fast:
        replay_header(session, len(events))
    else:
        click.echo(f"\n>>> REPLAY: {session} ({len(events)} events)\n")

    for i, event in enumerate(events):
        # Prepare previews
        input_preview = ""
        output_preview = ""
        error_msg = ""

        if event.input:
            input_preview = json.dumps(event.input)
            if len(input_preview) > 60:
                input_preview = input_preview[:57] + "..."

        # Prefer canonical_output for cleaner replay display
        output_to_show = (
            event.canonical_output if event.canonical_output is not None else event.output
        )
        if output_to_show:
            output_preview = json.dumps(output_to_show)
            if len(output_preview) > 60:
                output_preview = output_preview[:57] + "..."

        if event.error:
            error_msg = event.error.get("message", str(event.error))
            if len(error_msg) > 60:
                error_msg = error_msg[:57] + "..."

        # Display event
        replay_event(
            index=i,
            total=len(events),
            tool=event.tool,
            status=event.status,
            input_preview=input_preview,
            output_preview=output_preview,
            error_msg=error_msg,
            animate=not fast,
        )

        # Animation delay between events
        if not fast and i < len(events) - 1:
            delay = 0.3
            if event.timestamp_start and event.timestamp_end:
                try:
                    start = datetime.fromisoformat(event.timestamp_start.replace("Z", "+00:00"))
                    end = datetime.fromisoformat(event.timestamp_end.replace("Z", "+00:00"))
                    actual_duration = (end - start).total_seconds()
                    delay = min(max(actual_duration * 0.5, 0.1), 1.0)
                except Exception:
                    pass
            time.sleep(delay)

        click.echo()

    # Footer
    replay_footer()


@main.command()
@click.argument("session", required=False)
@click.option("--last", "-l", is_flag=True, help="Use most recent session")
def verify(session: str | None, last: bool):
    """Verify hash chain integrity.

    Checks that the session's event log has not been tampered with.

    EXIT CODES:
        0: Valid - hash chain intact
        1: Tampered - content modified or chain broken
        2: Truncated - incomplete write detected (crash recovery)
        3: Parse error - invalid JSON in event file
        4: Not found - session doesn't exist
    """
    session = _resolve_session(session, last)
    if session is None:
        if not last:
            click.echo("Error: Missing argument 'SESSION'. Use --last for most recent.", err=True)
        sys.exit(4)

    # Show spinner while verifying
    with spinner(f"Verifying {session}", style="dots") as s:
        # Brief animation
        for _ in range(5):
            s.spin()
            time.sleep(0.1)

        result = verify_session(session)

        if result.status == VerifyStatus.VALID:
            s.succeed(f"Session verified: {result.event_count} events")
        elif result.status == VerifyStatus.NOT_FOUND:
            s.fail(f"Session '{session}' not found.")
        elif result.status == VerifyStatus.TRUNCATED:
            s.warn(f"Truncation detected: {result.event_count} complete events")
        elif result.status == VerifyStatus.PARSE_ERROR:
            s.fail("Parse error in session")
        else:  # TAMPERED
            s.fail("Verification failed: TAMPERING DETECTED")

    # Additional details after spinner
    if result.status == VerifyStatus.VALID:
        click.echo(colorize("  Hash chain intact", DIM))
        sys.exit(0)

    elif result.status == VerifyStatus.NOT_FOUND:
        sys.exit(result.exit_code)

    elif result.status == VerifyStatus.TRUNCATED:
        click.echo(f"  {result.error_message}")
        if result.truncated_line:
            click.echo(colorize(f"  Partial data: {result.truncated_line}", DIM))
        click.echo(colorize("  This may indicate a crash during write.", DIM))
        sys.exit(result.exit_code)

    elif result.status == VerifyStatus.PARSE_ERROR:
        click.echo(f"  {result.error_message}")
        sys.exit(result.exit_code)

    else:  # TAMPERED
        click.echo(f"  {result.error_message}")
        if result.error_index is not None:
            click.echo(f"  Event index: {result.error_index}")
        if result.expected_hash and result.actual_hash:
            click.echo(f"  Expected: {result.expected_hash[:16]}...")
            click.echo(f"  Actual:   {result.actual_hash[:16]}...")
        sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
