"""Reading a run file, and looking a dataset up at telemetry write times."""

import json
from pathlib import Path

import numpy as np
import pytest
from wise_dynamics.basilisk.scenarios.leo500 import Leo500

from harness.runs import at, read_run

RUN = {
    "t_s": np.array([0.0, 0.5, 1.0, 1.5]),
    "truth/r_N": np.arange(12.0).reshape(4, 3),
}
"""A run recorded every 0.5 s."""


def test_at_gives_the_rows_at_each_write_time_repeats_included():
    """Each write time picks its recorded row, a time written twice picking it twice."""
    rows = at(RUN, "truth/r_N", np.array([0.5, 1.5, 1.5]))

    np.testing.assert_array_equal(rows, RUN["truth/r_N"][[1, 3, 3]])


@pytest.mark.parametrize("t_s", [2.0, 0.5 + 1e-9], ids=["after", "a-ns-off"])
def test_at_refuses_a_time_not_recorded_naming_it(t_s: float):
    """A time beyond or a nanosecond off the recorded ones is refused, not interpolated.

    Args:
        t_s: s, the time asked for.
    """
    with pytest.raises(KeyError, match=f"truth/r_N has no row at t = {t_s} s"):
        at(RUN, "truth/r_N", np.array([0.0, t_s]))


def test_read_run_gives_the_command_log_as_json(tmp_path: Path):
    """The `commands` attribute reads back as its JSON.

    Args:
        tmp_path: where the run file is written.
    """
    path = tmp_path / "run.h5"
    commands = [{"name": "nav.initNavState", "response": "OK"}]
    Leo500().vehicle.write_run_file(
        path,
        {"t_s": (RUN["t_s"], "s")},
        attrs={"commands": json.dumps(commands)},
    )

    run = read_run(path)

    assert json.loads(str(run["commands"])) == commands
