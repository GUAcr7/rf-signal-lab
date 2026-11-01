"""Inspect the supplied uImage header/banner read-only, without loading it."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

ROOT=Path(__file__).resolve().parents[1]
IMAGE=Path('D:/AD9361/AD9361/软件资料/Linux/Kernel/image/linux-xlnx-ad-fmcomms3-ebz/uImage')


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p31-kernel-image-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    blob=IMAGE.read_bytes()
    magic,header_crc,timestamp,size,load,entry,payload_crc,os_id,arch,kind,compression,name=struct.unpack('>7I4B32s',blob[:64])
    header=bytearray(blob[:64]);header[4:8]=bytes(4)
    report=dict(source=str(IMAGE),sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob),
        magic=hex(magic),header_crc_ok=zlib.crc32(header)==header_crc,
        payload_crc_ok=zlib.crc32(blob[64:64+size])==payload_crc,
        declared_payload_size=size,load_address=hex(load),entry=hex(entry),compression=compression,
        image_name=name.split(b'\0')[0].decode('ascii',errors='replace'),banners=[],
        board_operations=False,source_build_identity_proven=False)
    for match in re.finditer(b'\x1f\x8b\x08',blob):
        try:
            decoder=zlib.decompressobj(31)
            raw=decoder.decompress(blob[match.start():],64*1024*1024)
        except zlib.error:
            continue
        if decoder.eof:
            for banner in re.findall(rb'Linux version [^\x00\n]{1,500}',raw):
                report['banners'].append(dict(gzip_offset=match.start(),decompressed_bytes=len(raw),
                    decompressed_sha256=hashlib.sha256(raw).hexdigest(),text=banner.decode('utf-8',errors='replace')))
    report['status']='header_crc_and_embedded_banner_checked' if magic==0x27051956 and report['header_crc_ok'] and report['payload_crc_ok'] and report['banners'] else 'incomplete_or_invalid'
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(report['status'])
    for banner in report['banners']:
        print(banner['text'])


if __name__=='__main__':main()
