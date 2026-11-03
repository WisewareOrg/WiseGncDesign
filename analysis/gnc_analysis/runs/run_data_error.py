"""The error the run loader raises."""

__all__ = ["RunDataError"]


class RunDataError(Exception):
    """A run file, or a run directory, differs from what `load_run` and `load_run_directory`
    read. The message names the file and the dataset, attribute or rule at fault."""
