# Sync the sim, notebook and F´ groups at their locked versions, register the kernel and build the F´ deployment.
_sync:
    git submodule update --init --depth 1 cdh/fprime/lib/fprime
    uv sync --locked --group sim --group notebooks --group fprime
    uv run --no-sync python -m ipykernel install --sys-prefix --name wise-gnc-design --display-name "WiseGncDesign"
    just fsw

# Build the F´ deployment into gnc_cdh.fprime: its Python extension and its dictionary.
fsw:
    [ -d cdh/fprime/build-fprime-automatic-native ] || (cd cdh/fprime && uv run --no-sync fprime-util generate -DCMAKE_BUILD_TYPE=Release -DPython_EXECUTABLE="$(uv run --no-sync python -c 'import sys; print(sys.executable)')")
    uv run --no-sync cmake --build cdh/fprime/build-fprime-automatic-native --target _wise_fsw

# Install an editable WiseDynamics checkout and print the one in use.
local: _sync
    uv pip install -e "${WISE_DYNAMICS_PATH:-../WiseDynamics}[notebook]"
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupytext --sync $(grep -l '^#   jupytext:' algorithms/gnc_algorithms/*/*.py missions/*.py)

# Install the WiseDynamics commit in uv.lock and print the one in use.
pinned: _sync
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupytext --sync $(grep -l '^#   jupytext:' algorithms/gnc_algorithms/*/*.py missions/*.py)

# Open JupyterLab in this environment.
lab:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupyter lab

# Run the test suite: every Monte Carlo capped at two cases, the notebooks run end to end.
test *args:
    uv run --no-sync pytest {{args}}

# Make `name` the active Monte Carlo session; with no name, list the sessions.
session name="":
    uv run --no-sync pytest --sim-session {{name}}

# Judge the active session against the requirement analyzers.
judge *args:
    uv run --no-sync pytest analysis {{args}}

# Check the Doorstop requirements tree with wise-ci's check-reqs.
reqs:
    uv run --locked --project docs/requirements check-reqs --root docs/requirements

# Fly a notebook's Monte Carlo tests headless at full count into the active session; extra arguments go to pytest.
fly notebook *args:
    uv run --no-sync pytest {{notebook}} --full-monte-carlo {{args}}
