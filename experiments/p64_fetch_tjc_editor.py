"""Download official TJC editor to E:, verify ZIP and inspect only; never run it."""
from datetime import datetime,timezone
import hashlib,json,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL='http://filedown.tjc1688.com/USARTHMI/USARTHMIsetup_latest.zip'
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p64-tjc-editor-'+stamp);out.mkdir(exist_ok=False)
    dest=Path('E:/FPGA_Tools/Downloads')/('TJC-'+stamp);dest.mkdir(exist_ok=False)
    r=dict(status='downloading',URL=URL,destination=str(dest),software_executed=False,board_operations=False)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save();print(out,flush=True)
    try:
        package=dest/'USARTHMIsetup_latest.zip';count=0;digest=hashlib.sha256();maximum=512*1024*1024
        with urllib.request.urlopen(URL,timeout=30) as response,package.open('xb') as f:
            expected=int(response.headers['Content-Length']) if response.headers.get('Content-Length') else None
            if expected and expected>maximum:raise ValueError('Package exceeded size bound')
            r['final_URL']=response.url;r['expected_bytes']=expected;save()
            while True:
                block=response.read(1024*1024)
                if not block:break
                count+=len(block)
                if count>maximum:raise ValueError('Download exceeded bound')
                f.write(block);digest.update(block)
        if expected and expected!=count:raise ValueError('Truncated package')
        with zipfile.ZipFile(package) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC failed')
            r['members']=[dict(name=i.filename,bytes=i.file_size) for i in z.infolist()]
            # Extract bounded regular installer files only, never execute them.
            if sum(i.file_size for i in z.infolist())>1024*1024*1024:raise ValueError('Expanded bound')
            target=dest/'package';target.mkdir()
            for i in z.infolist():
                path=(target/i.filename).resolve()
                if target.resolve() not in path.parents:raise ValueError('Unsafe ZIP path')
                if i.is_dir():path.mkdir(parents=True,exist_ok=True);continue
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(i))
        r.update(status='downloaded_official_TJC_editor_ZIP_CRC_checked_not_run',package=str(package),bytes=count,
                 package_sha256=digest.hexdigest(),extracted_directory=str(target))
    except Exception as e:r.update(status='failed_or_incomplete_TJC_editor_download',error=repr(e))
    save();print(r['status'],flush=True)
    return 0 if r['status'].startswith('downloaded_') else 1
if __name__=='__main__':raise SystemExit(main())
