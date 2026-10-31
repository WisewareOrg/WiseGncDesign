# C&DH

The C&DH (command and data handling) partition, in the ARINC-653 sense: `bindings.py` is the
data dictionary of which input and output field each algorithm under `algorithms/` needs, in
transport-neutral names. Each transport that resolves this dictionary against its own messages
is a sibling directory here, holding only that transport's marshaling code.
