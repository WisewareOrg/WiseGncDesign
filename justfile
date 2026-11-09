# Install an editable WiseDynamics checkout and print the one in use.
local:
    uv pip install -e "${WISE_DYNAMICS_PATH:-../WiseDynamics}[notebook]"
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"

# Install the WiseDynamics commit in uv.lock and print the one in use.
pinned:
    uv sync --locked --group sim --group notebooks
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"

# Open JupyterLab in this environment.
lab:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupyter lab

# Run the test suite.
test:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync pytest

# Register the uv-project Jupyter kernel the algorithm notebooks name, once.
kernel:
    uv run --no-sync python -m ipykernel install --user --name uv-project --display-name "Python (uv)"
