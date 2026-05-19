"""Logging configuration for volcatenate.

All modules use ``from volcatenate.log import logger`` and call
``logger.info(...)``, ``logger.warning(...)``, etc.

By default the logger is **silent** (NullHandler).  Call
``setup_logging()`` — or set ``verbose`` / ``log_file`` in
:class:`~volcatenate.config.RunConfig` — to enable output.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("volcatenate")

# Tracks which log-file paths have been opened by this Python process.
# First time we see a path in a process, we truncate it; subsequent
# calls to ``setup_logging`` with the same path append.  This means a
# notebook or script that runs multiple ``calculate_*`` calls keeps
# all logs in one file instead of overwriting them on every call.
_log_files_opened: set[str] = set()


_TERMINAL_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def _resolve_terminal_level(level: str) -> int:
    """Convert a level name to the numeric logging constant.

    Accepts case-insensitive names from :data:`_TERMINAL_LEVELS`. Raises
    ``ValueError`` for anything else so misconfigured YAML fails loudly
    at setup time rather than silently dropping messages.
    """
    name = (level or "INFO").upper()
    if name not in _TERMINAL_LEVELS:
        raise ValueError(
            f"Unknown verbose_level {level!r}. "
            f"Choose one of: {sorted(_TERMINAL_LEVELS)}."
        )
    return getattr(logging, name)


def setup_logging(
    verbose: bool = False,
    log_file: str = "",
    console: object = None,
    level: str = "INFO",
) -> None:
    """Configure the ``volcatenate`` logger.

    Parameters
    ----------
    verbose : bool
        If *True*, print progress messages to stdout.  The threshold is
        controlled by *level*.
    log_file : str
        If non-empty, write **all** messages (DEBUG and above) to
        this file.  The file is **truncated on the first call within
        a Python process** and **appended** thereafter, so multiple
        ``calculate_*`` calls in the same notebook or script
        accumulate into one log instead of clobbering each other.
        Restarting Python (or calling :func:`reset_log_file_tracking`)
        starts a fresh file on the next call.  The level here is not
        affected by *level* — the file is always DEBUG so the runlog
        stays comprehensive.
    console : rich.console.Console, optional
        If provided and *verbose* is True, use ``RichHandler`` with
        this console instance.  This prevents progress bar corruption
        when both logging and progress bars are active.
    level : str, optional
        Terminal log level when *verbose* is True.  One of
        ``"DEBUG"``, ``"INFO"`` (default), ``"WARNING"``, ``"ERROR"``.

    Notes
    -----
    This is called automatically by the core entry-point functions
    (``calculate_saturation_pressure``, ``calculate_degassing``,
    ``run_comparison``) using the ``RunConfig.verbose``,
    ``RunConfig.verbose_level`` and ``RunConfig.log_file`` fields.

    Power users can also call it directly or configure the
    ``"volcatenate"`` logger with standard ``logging`` handlers.
    """
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    terminal_level = _resolve_terminal_level(level)

    if verbose:
        if console is not None:
            try:
                from rich.logging import RichHandler
                sh = RichHandler(
                    console=console,
                    show_time=False,
                    show_path=False,
                    markup=True,
                    level=terminal_level,
                )
                logger.addHandler(sh)
            except ImportError:
                import sys
                sh = logging.StreamHandler(sys.stdout)
                sh.setLevel(terminal_level)
                sh.setFormatter(logging.Formatter("%(message)s"))
                logger.addHandler(sh)
        else:
            import sys
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(terminal_level)
            sh.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(sh)

    if log_file:
        abs_path = os.path.abspath(log_file)
        # Truncate on first call per process; append thereafter.
        mode = "w" if abs_path not in _log_files_opened else "a"
        fh = logging.FileHandler(log_file, mode=mode)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(fh)
        _log_files_opened.add(abs_path)

    # If neither verbose nor log_file, stay silent
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())


def reset_log_file_tracking() -> None:
    """Forget which log files have been opened in this process.

    The next call to :func:`setup_logging` with a given ``log_file``
    will truncate it again.  Useful in long-running notebooks where
    you want to start a fresh log mid-session.
    """
    _log_files_opened.clear()
