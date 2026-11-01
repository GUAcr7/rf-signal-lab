"""Standalone 1024-point FFT vectors: NumPy theory and installed Xilinx bit-accurate model.

No board access. The vendor DLL/header/license remain in the extracted bundle.
Signed 16-bit input counts map to Q1.15; unscaled output retains 15 fractional
bits, so multiply model doubles by 32768 to recover signed 27-bit counts.
The numerical acceptance limit is declared here before running: maximum complex
error <=64 output counts versus NumPy's double-precision FFT. This is a module
engineering tolerance, not RF measurement accuracy. Axis order is native FFT,
not fftshift; no Hann window is applied inside this module.
"""

import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/data/ip/xilinx/xfft_v9_1/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip')
N = 1024
MAX_COMPLEX_ERROR_COUNTS = 64.
DP = C.POINTER(C.c_double)
IP = C.POINTER(C.c_int)


class Generics(C.Structure):
    _fields_ = [(name, C.c_int) for name in ('C_NFFT_MAX', 'C_ARCH', 'C_HAS_NFFT', 'C_USE_FLT_PT',
                'C_INPUT_WIDTH', 'C_TWIDDLE_WIDTH', 'C_HAS_SCALING', 'C_HAS_BFP', 'C_HAS_ROUNDING')]


class Inputs(C.Structure):
    _fields_ = [('nfft', C.c_int), ('xn_re', DP), ('xn_re_size', C.c_int),
                ('xn_im', DP), ('xn_im_size', C.c_int), ('scaling_sch', IP),
                ('scaling_sch_size', C.c_int), ('direction', C.c_int)]


class Outputs(C.Structure):
    _fields_ = [('xk_re', DP), ('xk_re_size', C.c_int), ('xk_im', DP),
                ('xk_im_size', C.c_int), ('blk_exp', C.c_int), ('overflow', C.c_int)]


def vectors():
    n = np.arange(N)
    rng = np.random.default_rng(70209361)
    impulse = np.zeros(N, dtype=complex)
    impulse[0] = 1024-512j
    result = {'zero': np.zeros(N, complex), 'dc': np.full(N, 1024-256j), 'impulse': impulse,
              'positive_bin_73': 1024*np.exp(2j*np.pi*73*n/N),
              'negative_bin_129': 1024*np.exp(-2j*np.pi*129*n/N),
              'off_bin_73_25': 1024*np.exp(2j*np.pi*73.25*n/N),
              'random_adc12': rng.integers(-2048,2048,N)+1j*rng.integers(-2048,2048,N),
              'full_width_alternating': np.where(n%2,32767,-32768)+1j*np.where(n%4<2,32767,-32768)}
    dataset = ROOT/'data/p08-synthetic-v1-20261011T053828Z'
    manifest = json.loads((dataset/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['source'] == 'SYNTHETIC_NOT_REAL_RF'
    provenance = {}
    for label in ('BPSK','QPSK','16QAM'):
        row = next(r for r in manifest['records'] if r['modulation']==label and r['split']=='validation' and r['nominal_snr_db']==20)
        path = dataset/row['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['file_sha256']
        with np.load(path,allow_pickle=False) as data:
            iq = data['noisy'][:N].copy()
        result['synthetic_'+label] = iq/max(np.max(np.abs(iq.real)),np.max(np.abs(iq.imag)))*1800
        provenance['synthetic_'+label] = {'record_id':row['record_id'],'sha256':row['file_sha256'],
                                         'purpose':'FFT arithmetic only; not new modulation recognition accuracy'}
    return {name:np.rint(iq.real).astype(np.int64)+1j*np.rint(iq.imag).astype(np.int64) for name,iq in result.items()},provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--architecture',choices=('radix2','pipelined'),default='radix2')
    args = parser.parse_args()
    out = args.out or ROOT/'results'/datetime.now(timezone.utc).strftime('p07-fft-vectors-%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True,exist_ok=False)
    bundle_dir = out/'vendor-cmodel'
    bundle_dir.mkdir()
    with zipfile.ZipFile(BUNDLE) as archive:
        for name in archive.namelist():
            if not name.endswith('/'):
                # Known local bundle; flatten names, never use archive paths as destinations.
                target = bundle_dir/Path(name).name
                if target.exists(): raise ValueError('Duplicate vendor filename')
                target.write_bytes(archive.read(name))
    dll_context = os.add_dll_directory(str(bundle_dir.resolve()))
    dll = C.CDLL(str((bundle_dir/'libIp_xfft_v9_1_bitacc_cmodel.dll').resolve()))
    create = dll.xilinx_ip_xfft_v9_1_create_state
    create.argtypes,create.restype = [Generics],C.c_void_p
    destroy = dll.xilinx_ip_xfft_v9_1_destroy_state
    destroy.argtypes,destroy.restype = [C.c_void_p],None
    simulate = dll.xilinx_ip_xfft_v9_1_bitacc_simulate
    simulate.argtypes,simulate.restype = [C.c_void_p,Inputs,C.POINTER(Outputs)],C.c_int
    generics = Generics(10,2 if args.architecture=='radix2' else 3,0,0,16,24,0,0,1)
    state = create(generics)
    if not state: raise RuntimeError('Vendor FFT model state allocation failed')
    items,provenance = vectors()
    inputs_hex,expected_hex,reports = [],[],[]
    np_arrays = {}
    try:
        for name,iq in items.items():
            assert iq.shape==(N,) and np.all(iq.real>=-32768) and np.all(iq.real<=32767)
            assert np.all(iq.imag>=-32768) and np.all(iq.imag<=32767)
            real,imag = np.ascontiguousarray(iq.real/32768),np.ascontiguousarray(iq.imag/32768)
            yr,yi = np.zeros(N),np.zeros(N)
            schedule = np.zeros(10,dtype=np.int32)
            inp = Inputs(10,real.ctypes.data_as(DP),N,imag.ctypes.data_as(DP),N,schedule.ctypes.data_as(IP),10,1)
            result = Outputs(yr.ctypes.data_as(DP),N,yi.ctypes.data_as(DP),N,0,0)
            if simulate(state,inp,C.byref(result))!=0: raise RuntimeError('Vendor FFT model failed: '+name)
            assert result.xk_re_size==result.xk_im_size==N
            output = (yr+1j*yi)*32768
            assert np.all(output.real==np.rint(output.real)) and np.all(output.imag==np.rint(output.imag))
            golden = np.fft.fft(iq)
            error = float(np.max(np.abs(output-golden)))
            assert error<=MAX_COMPLEX_ERROR_COUNTS, (name,error)
            if name in ('zero','dc','impulse'): np.testing.assert_array_equal(output,golden)
            if name=='positive_bin_73': assert np.argmax(np.abs(output))==73
            if name=='negative_bin_129': assert np.argmax(np.abs(output))==N-129
            assert np.all(np.abs(output.real)<2**26) and np.all(np.abs(output.imag)<2**26)
            for x,y in zip(iq,output,strict=True):
                inputs_hex.append(f'{int(x.imag)&0xffff:04x}{int(x.real)&0xffff:04x}')
                # AXIS output components occupy 32-bit padded fields; valid 27-bit
                # signed data are compared by selecting [26:0] and [58:32].
                expected_hex.append(f'{int(y.imag)&0xffffffff:08x}{int(y.real)&0xffffffff:08x}')
            reports.append({'name':name,'max_complex_error_counts':error,'output_peak_bin':int(np.argmax(np.abs(output))),
                            'input_peak_component_counts':float(max(np.max(np.abs(iq.real)),np.max(np.abs(iq.imag))))})
            np_arrays[name+'_input']=iq
            np_arrays[name+'_expected']=output
            np_arrays[name+'_numpy']=golden
    finally:
        destroy(state)
        dll_context.close()
    (out/'inputs.hex').write_text('\n'.join(inputs_hex)+'\n',encoding='ascii')
    (out/'expected.hex').write_text('\n'.join(expected_hex)+'\n',encoding='ascii')
    np.savez(out/'reference.npz',**np_arrays)
    verification={'schema':'rfsig.fft.reference.v1','architecture':args.architecture,'frames':len(items),'points_per_frame':N,
                  'input_bits':16,'output_bits':27,'output_axis_component_padding_bits':32,
                  'direction':'forward','order':'natural','scaling':'unscaled','window':'none',
                  'clock_target_hz':100000000,'numeric_acceptance_limit_counts':MAX_COMPLEX_ERROR_COUNTS,
                  'cmodel_generics':{name:getattr(generics,name) for name,_ in Generics._fields_},
                  'ctypes_struct_sizes':[C.sizeof(Generics),C.sizeof(Inputs),C.sizeof(Outputs)],
                  'cases':reports,'synthetic_provenance':provenance,'board_accessed':False,'rf_accuracy_verified':False,
                  'bundle':str(BUNDLE),'bundle_sha256':hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
                  'vendor_files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle_dir.iterdir()},
                  'vectors_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('inputs.hex','expected.hex','reference.npz')}}
    (out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    main()
