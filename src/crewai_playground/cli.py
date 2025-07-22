#!/usr/bin/env python3
"""CLI interface for CrewAI Playground."""

import click
import sys
from . import __version__


@click.group()
def cli():
    """CrewAI Playground - Web UI for CrewAI chat functionality."""
    pass


@cli.command()
def version():
    """Show the version of CrewAI Playground."""
    click.echo(f"CrewAI Playground version {__version__}")


@cli.command()
def start():
    """Start the CrewAI Playground server."""
    # Import server module only when needed to avoid FastAPI initialization issues
    from .server import start_server
    start_server()


def main():
    """Main entry point - defaults to start command for backward compatibility."""
    if len(sys.argv) == 1:
        # No arguments provided, default to start command
        sys.argv.append('start')
    cli()


if __name__ == "__main__":
    main()
