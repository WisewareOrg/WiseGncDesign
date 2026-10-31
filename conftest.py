"""Loads WiseDynamics' Basilisk plant and campaign-option fixtures as a pytest plugin for the
whole suite. Must sit at the repository root: pytest requires `pytest_plugins` declarations to
be in a top-level conftest, not one nested under a test subdirectory such as tests/sim/."""

pytest_plugins = ["sim.basilisk.pytest_plugin"]
