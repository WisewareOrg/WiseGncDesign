# Sync the sim and notebook groups at the locked WiseDynamics commit and register the kernel.
_sync:
    uv sync --locked --group sim --group notebooks
    uv run --no-sync python -m ipykernel install --sys-prefix --name wise-gnc-design --display-name "WiseGncDesign"

# Install an editable WiseDynamics checkout and print the one in use.
local: _sync
    uv pip install -e "${WISE_DYNAMICS_PATH:-../WiseDynamics}[notebook]"
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupytext --sync algorithms/gnc_algorithms/*.py

# Install the WiseDynamics commit in uv.lock and print the one in use.
pinned: _sync
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupytext --sync algorithms/gnc_algorithms/*.py

# Open JupyterLab in this environment.
lab:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupyter lab

# Run the test suite.
test:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync pytest
