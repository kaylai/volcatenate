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

    def __enter__(self) -> "VolcProgress":
        if not self._enabled:
            return self
        try:
            from rich.progress import (
                Progress,
                SpinnerColumn,
                TextColumn,
                BarColumn,
                MofNCompleteColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )
            from rich.console import Console

            self._console = Console()
            self._progress = Progress(
                SpinnerColumn("earth"),
                TextColumn("[bold orange1]\U0001f30b"),
                TextColumn("[bold white]{task.description}"),
                BarColumn(
                    bar_width=30,
                    style="bright_black",
                    complete_style="bold red",
                    finished_style="bold green",
                ),
                MofNCompleteColumn(),
                TextColumn("[dim]\u2022"),
                TimeElapsedColumn(),
                TextColumn("[dim]/"),
                TimeRemainingColumn(),
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
