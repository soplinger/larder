"""Shared test helpers. Scratch files live inside the project, never in the system temp dir."""

import os
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-10-17"


def scratch_dir():
    """A temporary directory created inside the project, removed when the context exits."""
    return tempfile.TemporaryDirectory(dir=PROJECT_ROOT, prefix=".test-scratch-")


def run_cli(*argv):
    """Run the CLI and return (exit_code, stdout, stderr)."""
    from larder.cli import main

    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()
