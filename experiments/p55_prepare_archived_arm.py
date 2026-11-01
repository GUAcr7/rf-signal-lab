"""Adapt the corrected deployment-only driver for archived inputs after reboot."""
from p45_checkpoint import ROOT

def main():
    text=(ROOT/'experiments/p55_arm_verify.py').read_text('utf-8')
    text=text.replace('import argparse,json,re','import argparse,json,re,gzip,hashlib',1)
    anchor="    def save():write(out/'report.json',r)"
    extra='''    preflight=read(ROOT/'results/p46-preflight-20261024T074202Z/report.json')
    if preflight['status']!='read_only_both_boards_identified_DMA_idle':raise ValueError('current preflight required')
    r['input_origin_boot']=r['expected_boot'];r['expected_boot']=preflight['boards']['COM8']['boot_id']
    r['scope']='current ARM execution on archived independent RF from prior boot; no new RF acquisition'
    payload=[]
    for item in ev['fixtures']:
        path=ROOT/item['path']
        if sha(path)!=item['sha256'] or path.stat().st_size!=262144:raise ValueError('archived fixture changed')
        payload.append(path.read_bytes())
    all_raw=b''.join(payload);packet=gzip.compress(all_raw,compresslevel=1,mtime=0)
    (out/'archived-inputs.bin.gz').write_bytes(packet)
    r.update(archived_input_bytes=len(all_raw),archive_sha256=hashlib.sha256(packet).hexdigest(),
        decompressed_sha256=hashlib.sha256(all_raw).hexdigest(),archived_inputs_uploaded_to_RAM=True,
        current_boot_RF_capture=False,preflight='results/p46-preflight-20261024T074202Z/report.json')
'''
    if text.count(anchor)!=1:raise ValueError('record anchor')
    text=text.replace(anchor,extra+anchor)
    before="        r['status']='running_frozen_ARM_inference';save();verified_files={}"
    after='''        board.command("PS1='# '")
        upload(board,remote+'/z',packet)
        board.command("PS1=''");board.command('stty -echo')
        board.command('z='+remote+'/z');board.command('gzip -t $z')
        board.command('gzip -dc $z > '+remote+'/all')
        if digest(remote+'/all')!=r['decompressed_sha256']:raise ValueError('archived input bundle mismatch')
        r['status']='running_frozen_ARM_inference';save();verified_files={}'''
    if text.count(before)!=1:raise ValueError('upload anchor')
    text=text.replace(before,after).replace("        for fixture in ev['fixtures']:","        for fixture_index,fixture in enumerate(ev['fixtures']):",1)
    start=text.index("            src=case['remote'].removesuffix('.gz')")
    end=text.index("            if digest(remote+'/x')!=fixture['sha256']",start)
    replacement="            board.command('s='+remote+'/all')\n            board.command('dd if=$s of=$x bs=262144 skip='+str(fixture_index)+' count=1')\n"
    text=text[:start]+replacement+text[end:]
    target=ROOT/'experiments/p55_arm_archived.py'
    if target.exists():raise ValueError('preserve existing generated driver')
    target.write_text(text,encoding='utf-8');print(target)
if __name__=='__main__':main()
