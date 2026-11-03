"""Run analysis: loads recorded runs (`runs`), computes each run's attitude, position and
velocity error against truth (`error_metrics`), writes their report (`report`, and the
`gnc-analyze` command in `cli`), bounds the dead reckoner's error (`error_bounds`), with its own
MRP math (`mrp`)."""
