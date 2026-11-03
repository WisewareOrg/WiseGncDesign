"""The C&DH (command and data handling) partition: a data dictionary of each algorithm's inputs
and outputs in neutral role and signal names (`data_dictionary`), the structural types a hosted
algorithm satisfies (`hosted_algorithm`, `hosted_state`), the frame transforms a host applies
(`frames`), and one subpackage per transport that resolves the dictionary against its own
messages."""

from gnc_cdh.algorithm_binding import AlgorithmBinding
from gnc_cdh.data_dictionary import BINDINGS, binding
from gnc_cdh.hosted_algorithm import HostedAlgorithm
from gnc_cdh.hosted_state import HostedState
from gnc_cdh.input_signal import InputSignal
from gnc_cdh.output_signal import OutputSignal

__all__ = [
    "BINDINGS",
    "AlgorithmBinding",
    "HostedAlgorithm",
    "HostedState",
    "InputSignal",
    "OutputSignal",
    "binding",
]
