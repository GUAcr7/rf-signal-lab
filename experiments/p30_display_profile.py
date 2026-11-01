"""Retain and inspect the actual vendor 800x480 overlay, not an assumed timing."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import struct
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def properties(data):
    header=struct.unpack_from('>10I',data)
    magic,total,off_struct,off_strings,_,version,_,_,size_strings,size_struct=header
    if magic!=0xd00dfeed or total>len(data) or version<17:raise ValueError('invalid modern FDT')
    strings=data[off_strings:off_strings+size_strings]
    index=off_struct;end=off_struct+size_struct;stack=[];result={}
    while index<end:
        token=struct.unpack_from('>I',data,index)[0];index+=4
        if token==1:
            stop=data.index(b'\0',index,end)
            stack.append(data[index:stop].decode('ascii'));index=(stop+4)&~3
        elif token==2:stack.pop()
        elif token==3:
            size,nameoff=struct.unpack_from('>2I',data,index);index+=8
            if index+size>end:raise ValueError('property outside struct block')
            name=strings[nameoff:strings.index(b'\0',nameoff)].decode('ascii')
            raw=data[index:index+size];index=(index+size+3)&~3
            value=dict(hex=raw.hex())
            if len(raw)%4==0:value['u32']=list(struct.unpack('>'+str(len(raw)//4)+'I',raw))
            if raw and all(x==0 or 32<=x<=126 for x in raw):value['strings']=raw.rstrip(b'\0').decode('ascii').split('\0')
            result['/'.join(stack)+'/'+name]=value
        elif token==4:pass
        elif token==9:return result
        else:raise ValueError('unknown FDT token '+str(token))
    raise ValueError('FDT_END absent')


def main():
    source=Path('D:/xilinx/xilinx/4-软件资料/Demo.zip')
    prefix='All-Programmable-SoC-demos/axi_video_display_demo/sw/linux_system/image/'
    out=ROOT/'results'/('p30-display-profile-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    records=[]
    with zipfile.ZipFile(source) as archive:
        for name in ['axi-video-display-480p.dtbo','video_timing_config.sh','axi_vdma.sh']:
            data=archive.read(prefix+name);(out/name).write_bytes(data)
            records.append(dict(member=prefix+name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    decoded=properties((out/'axi-video-display-480p.dtbo').read_bytes())
    (out/'overlay-properties.json').write_text(json.dumps(decoded,indent=2)+'\n',encoding='utf-8')
    timing={k:v for k,v in decoded.items() if any(word in k for word in ['hactive','vactive','clock-frequency','front-porch','back-porch','sync-len'])}
    report=dict(status='vendor_profile_read_only_archived',archive=str(source),files=records,timing=timing,
        board_operations=False,limitations=['Decoded values do not prove active hardware timing or DRM programming'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(json.dumps(timing,indent=2))


if __name__=='__main__':main()
