"""Each gate script, run under GNU grep in a temporary tree: a clean tree passes, a seeded
violation fails, a legal line spelled like a violation passes, a broken pattern errors, and a
missing target errors."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

CLEAN = "import numpy as np\n"

# gate -> (file it writes into, seeded violations, legal lines spelled like one)
CASES = {
    "check-no-framework.sh": (
        "algorithms/gnc_algorithms/module.py",
        [
            "from Basilisk.architecture import messaging\n",
            "import fprime_gds\n",
            "osal_api()\n",
            "cfe_es_init()\n",
            '#include "cfe.h"\n',
            '#include "osapi.h"\n',
            "class TrickHLAFederate:\n",
            "#include <trick/MemoryManager.hh>\n",
        ],
        ["# a proposal for a tricky case\n", "# the trickle of a basil leaf\n"],
    ),
    "check-cdh-independent.sh": (
        "cdh/gnc_cdh/module.py",
        ["from wise_dynamics.basilisk import run_case\n", "import WiseDynamics\n"],
        ["# the dynamics of the spacecraft\n"],
    ),
    "check-cdh-dictionary-neutral.sh": (
        "cdh/gnc_cdh/bindings.py",
        ["reader_type = IMUSensorMsgReader\n", "from gnc_cdh import basilisk\n", "'r_BN_N'\n"],
        ['InputSignal("imu", "angular_rate", "omega_B", frame="platform_to_body")\n'],
    ),
    "check-cdh-transport-generic.sh": (
        "cdh/gnc_cdh/basilisk/fsw.py",
        ["def read_imu(self):\n", "simulatedImuSample = None\n", "dcm_PB = None\n"],
        ["# a transform of each payload field\n"],
    ),
    "check-analysis-independent.sh": (
        "analysis/gnc_analysis/module.py",
        ["from gnc_algorithms.mrp import angle\n", "import os, gnc_cdh\n", "import Basilisk\n"],
        ['"""Grades gnc_algorithms output against truth."""\n'],
    ),
}

# Files outside a gate's scope that carry its vocabulary, so a passing clean tree shows the
# scope is honoured.
OUT_OF_SCOPE = {
    "check-cdh-dictionary-neutral.sh": ("cdh/gnc_cdh/basilisk/signals.py", "messaging.NavAttMsg\n"),
    "check-cdh-transport-generic.sh": ("cdh/gnc_cdh/basilisk/signals.py", '("imu", "x")\n'),
}

# Generic modules every transport-generic tree holds besides the one written by CASES.
GENERIC_MODULES = ("cdh/gnc_cdh/basilisk/__init__.py", "cdh/gnc_cdh/basilisk/algorithm_module.py")


def _tree(root: Path, gate: str, line: str) -> Path:
    target, _, _ = CASES[gate]
    shutil.copy(SCRIPTS / gate, root / gate)
    for relative in (target, *GENERIC_MODULES):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(CLEAN)
    (root / target).write_text(CLEAN + line)
    if gate in OUT_OF_SCOPE:
        relative, text = OUT_OF_SCOPE[gate]
        (root / relative).write_text(text)
    return root / gate


def _run(script: Path) -> int:
    return subprocess.run(["bash", script.name], cwd=script.parent, capture_output=True).returncode


@pytest.mark.parametrize("gate", sorted(CASES))
def test_a_clean_tree_passes(gate, tmp_path):
    assert _run(_tree(tmp_path, gate, "")) == 0


@pytest.mark.parametrize(
    ("gate", "line"), [(g, line) for g, (_, bad, _) in CASES.items() for line in bad]
)
def test_a_seeded_violation_fails(gate, line, tmp_path):
    assert _run(_tree(tmp_path, gate, line)) == 1


@pytest.mark.parametrize(
    ("gate", "line"), [(g, line) for g, (_, _, legal) in CASES.items() for line in legal]
)
def test_a_legal_line_spelled_like_a_violation_passes(gate, line, tmp_path):
    assert _run(_tree(tmp_path, gate, line)) == 0


@pytest.mark.parametrize("gate", sorted(CASES))
def test_a_broken_pattern_errors(gate, tmp_path):
    script = _tree(tmp_path, gate, "")
    text = script.read_text()
    assert text.count("pattern='") == 1 or text.count("banned='") == 1
    script.write_text(text.replace("pattern='", "pattern='(").replace("banned='", "banned='("))

    assert _run(script) == 2


@pytest.mark.parametrize("gate", sorted(CASES))
def test_a_missing_target_errors(gate, tmp_path):
    shutil.copy(SCRIPTS / gate, tmp_path / gate)

    assert _run(tmp_path / gate) == 2


def test_every_gate_script_has_cases():
    assert sorted(p.name for p in SCRIPTS.glob("check-*.sh")) == sorted(CASES)
