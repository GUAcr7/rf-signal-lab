"""Run from the extracted kit: python example_read.py. No board is contacted."""
from pathlib import Path
import numpy as np
from data_api import load_kit


def main():
    manifest,records=load_kit(Path(__file__).resolve().parent)
    for name,record in records.items():
        # Choose ONE DMA buffer; do not flatten buffers across unknown gaps.
        x=record.iq[0]
        print(f'{record.label}: {record.iq.shape}, {x.dtype}; Fs=30.72 MS/s; '
              f'first DMA mean(I^2+Q^2)={np.mean(abs(x.astype(np.complex128))**2):.3f} counts^2')
    print('Known TX labels; not AI predictions. No independent training/test split.')
    return 0


if __name__=='__main__':raise SystemExit(main())
