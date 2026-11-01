import hashlib,json,tarfile
from pathlib import Path
out=Path(__file__).parent
src=Path('D:/AD9361/AD9361/软件资料/Linux/Kernel/src/linux-xlnx-ad-fmcomms3-ebz.tar.gz')
found=[]
with tarfile.open(src,'r|gz') as tf:
    for entry in tf:
        name=entry.name
        selected=entry.isfile() and (('wizard' in name.lower() and name.endswith(('.c','.h','.txt'))) or name.endswith(('xilinx_drm_crtc.c','xilinx_drm_encoder.c')))
        if not selected:continue
        data=tf.extractfile(entry).read()
        dest=out/('source-'+name.replace('/','__'))
        dest.write_bytes(data)
        found.append(dict(member=name,file=dest.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
(out/'driver-sources.json').write_text(json.dumps(dict(archive=str(src),archive_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),files=found,archive_modified=False,exact_running_source_match_proven=False),indent=2)+'\n',encoding='utf-8')
print(json.dumps(found,indent=2))
