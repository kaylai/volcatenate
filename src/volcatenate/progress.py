"""Rich progress bar utilities for volcatenate.

Provides a volcano-themed progress bar that works in both
terminals and Jupyter notebooks.  Rich auto-detects the
environment, so no special handling is needed.

Usage within volcatenate internals::

    from volcatenate.progress import VolcProgress

    with VolcProgress(total=20, description="Saturation pressures") as vp:
        for model in models:
            vp.update_model(model)
            for sample in samples:
                do_work()
                vp.advance()
"""

from __future__ import annotations

import warnings
from typing import Optional


class VolcProgress:
    """Context manager wrapping a Rich Progress bar with volcano theming.

    If ``enabled=False``, all methods are silent no-ops, so callers
    never need to check — they just call ``advance()`` etc.

    Parameters
    ----------
    total : int
        Total number of steps (models, samples, etc.).
    description : str
        Label shown on the left side of the bar.
    enabled : bool
        If *False*, the progress bar is not displayed and all
        methods become no-ops.
    """

    def __init__(
        self,
        total: int,
        description: str = "Processing",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._total = total
        self._description = description
        self._progress = None
        self._task_id = None
        self._console = None
        self._warnings: list[str] = []

    def __enter__(self) -> "VolcProgress":
        if not self._enabled:
            return self
        try:
            from rich.progress import (
                Progress,
                TextColumn,
                BarColumn,
                MofNCompleteColumn,
                TimeElapsedColumn,
            )
            from rich.console import Console

            self._console = Console()
            self._progress = Progress(
                TextColumn("{task.description}"),
                BarColumn(bar_width=30),
                MofNCompleteColumn(),
                TextColumn("[dim]\u2022"),
                TimeElapsedColumn(),
                console=self._console,
                transient=False,
            )
            self._progress.__enter__()
            self._task_id = self._progress.add_task(
                self._description, total=self._total,
            )
        except ImportError:
            self._enabled = False
        return self

    def __exit__(self, *exc_info) -> None:
        if self._progress is not None:
            self._progress.__exit__(*exc_info)
            self._progress = None
        # Emit accumulated warnings now that the bar is gone
        self._flush_warnings()

    def add_warning(self, message: str) -> None:
        """Queue a warning to be emitted after the progress bar closes.

        When no progress bar is active (disabled), the warning is
        emitted immediately via ``warnings.warn()``.
        """
        if self._progress is not None:
            # Bar is active — stash for later
            self._warnings.append(message)
        else:
            # No bar — emit right away
            warnings.warn(message, stacklevel=2)

    def _flush_warnings(self) -> None:
        """Emit all queued warnings now (called in __exit__)."""
        for msg in self._warnings:
            warnings.warn(msg, stacklevel=4)
        self._warnings.clear()

    def advance(self, n: int = 1) -> None:
        """Move the bar forward by *n* steps."""
        if self._progress is not None and self._task_id is not None:
            self._progress.advance(self._task_id, advance=n)

    def update_model(self, model_name: str) -> None:
        """Update the description to show which model is running."""
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=(
                    f"{self._description}"
                    f" [dim]\u2022[/dim] [bold cyan]{model_name}[/bold cyan]"
                ),
            )

    def update_description(self, text: str) -> None:
        """Replace the base description text."""
        if self._progress is not None and self._task_id is not None:
            self._description = text
            self._progress.update(self._task_id, description=text)

    def update_total(self, new_total: int) -> None:
        """Change the total (useful when models are skipped)."""
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, total=new_total)

    @property
    def console(self) -> Optional[object]:
        """Return the Rich Console instance (for RichHandler integration)."""
        return self._console

    @property
    def enabled(self) -> bool:
        return self._enabled
