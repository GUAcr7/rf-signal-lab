"""Run the first Level 0 BPSK mapping example."""

import numpy as np

from rfsig import map_bpsk


bits = np.array([1, 0, 0, 1])
symbols = map_bpsk(bits)

print("bits:   ", bits)
print("symbols:", symbols)
