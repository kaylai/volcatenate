"""Logging configuration for volcatenate.

All modules use ``from volcatenate.log import logger`` and call
``logger.info(...)``, ``logger.warning(...)``, etc.

By default the logger is **silent** (NullHandler).  Call
``setup_logging()`` — or set ``verbose`` / ``log_file`` in
:class:`~volcatenate.config.RunConfig` — to enable output.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("volcatenate")


def setup_logging(verbose: bool = False, log_file: str = "") -> None:
    """Configure the ``volcatenate`` logger.

    Parameters
    ----------
    verbose : bool
        If *True*, print progress messages to stdout (INFO level).
    log_file : str
        If non-empty, write **all** messages (DEBUG and above) to
        this file.  The file is overwritten each run.

    Notes
    -----
    This is called automatically by the core entry-point functions
    (``calculate_saturation_pressure``, ``calculate_degassing``,
    ``run_comparison``) using the ``RunConfig.verbose`` and
    ``RunConfig.log_file`` fields.

    Power users can also call it directly or configure the
    ``"volcatenate"`` logger with standard ``logging`` handlers.
    """
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    if verbose:
        import sys
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(sh)

    if log_file:
        fh = logging.FileHandler(log_file, mode="w")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(fh)

    # If neither verbose nor log_file, stay silent
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
