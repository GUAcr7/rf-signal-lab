"""Cross compile current RX diagnostic using the installed verified ARM compiler."""
from datetime import datetime,timezone
import hashlib,json,subprocess
from pathlib import Path
from p22_acquire_comparison import ROOT

TOOL=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')

def posix(path):
    s=Path(path).resolve().as_posix()
    return '/mnt/'+s[0].lower()+s[2:]


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p27-native-build-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source=ROOT/'embedded/arm_rx_diagnostic/arm_rx_diagnostic.c'
    header=ROOT/'embedded/vendor/libiio-v0.24/iio.h'
    original=json.loads((header.parent/'source.json').read_text('utf-8-sig'))
    if hashlib.sha256(header.read_bytes()).hexdigest()!=original['sha256']:raise RuntimeError('header changed')
    binary=out/'arm-rx-diagnostic'
    args=['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
          '-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',posix(header.parent),posix(source),'-o',posix(binary),'-ldl','-lrt']
    result=subprocess.run(args,capture_output=True,timeout=90)
    (out/'compile.stdout').write_bytes(result.stdout);(out/'compile.stderr').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
    elf=subprocess.run(['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(binary)],capture_output=True,timeout=20)
    (out/'elf.txt').write_bytes(elf.stdout)
    text=elf.stdout.decode()
    if elf.returncode or 'ELF32' not in text or 'VFP registers' not in text or '/lib/ld-linux-armhf.so.3' not in text:
        raise RuntimeError('unexpected ELF target')
    report={'status':'cross_compile_verified','binary':str(binary),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'compiler_argv':args,'RF_attributes_written':False,
            'header':original,'actual_receiver_libiio_required':'0.20','board_execution':'pending'}
    (out/'source.c').write_bytes(source.read_bytes())
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)


if __name__=='__main__':main()
