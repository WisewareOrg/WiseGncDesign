# Every recipe is --no-sync, so a plain sync never swaps the WiseDynamics in use, and prints it.

local:
    uv pip install -e "${WISE_DYNAMICS_PATH:-../WiseDynamics}[notebook]"
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"

pinned:
    uv sync --locked --group sim --group notebooks
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"

lab:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync jupyter lab

test:
    uv run --no-sync python -c "import wise_dynamics; print(wise_dynamics.__file__)"
    uv run --no-sync pytest

kernel:
    uv run --no-sync python -m ipykernel install --user --name uv-project --display-name "Python (uv)"
