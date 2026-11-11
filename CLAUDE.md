# Working rules

- **Edit an algorithm notebook through its `.ipynb`.** The owner works in `algorithms/gnc_algorithms/<name>/<name>.ipynb`. Edit that file, then run `uv run --no-sync jupytext --sync <name>.ipynb` so the paired `.py` matches, and commit the `.py` (`*.ipynb` is gitignored). Before editing, run the same sync and confirm it changes nothing; if it would, the owner has unsynced work, so stop and ask.
