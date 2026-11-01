"""Read MSI tables and expand its external CAB to E: without installing MSI.

No MSI custom actions, registry changes, drivers, board access or app launch.
"""
from datetime import datetime,timezone
import ctypes as C
from ctypes import wintypes as W
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p65-editor-unpack-'+stamp);out.mkdir(exist_ok=False)
    source=Path('E:/FPGA_Tools/Downloads/TJC-20261025T060628Z/extracted')
    dest=Path('E:/FPGA_Tools')/('TJC-USARTHMI-'+stamp);dest.mkdir(exist_ok=False)
    api=C.WinDLL('msi');handle=C.c_uint
    def function(name,args,restype=W.UINT):
        f=getattr(api,name);f.argtypes=args;f.restype=restype;return f
    open_database=function('MsiOpenDatabaseW',[W.LPCWSTR,W.LPCWSTR,C.POINTER(handle)])
    open_view=function('MsiDatabaseOpenViewW',[handle,W.LPCWSTR,C.POINTER(handle)])
    execute=function('MsiViewExecute',[handle,handle]);fetch=function('MsiViewFetch',[handle,C.POINTER(handle)])
    get_string=function('MsiRecordGetStringW',[handle,W.UINT,W.LPWSTR,C.POINTER(W.DWORD)])
    close=function('MsiCloseHandle',[handle])
    def field(record,index):
        length=W.DWORD(0);rc=get_string(record,index,None,C.byref(length))
        if rc not in (0,234):raise OSError('MSI string length '+str(rc))
        buf=C.create_unicode_buffer(length.value+1);length.value+=1
        rc=get_string(record,index,buf,C.byref(length))
        if rc:raise OSError('MSI string '+str(rc))
        return buf.value
    db=handle();rc=open_database(str(source/'USART HMI.msi'),None,C.byref(db))
    if rc:raise OSError('MSI database open '+str(rc))
    def query(sql,count):
        view=handle();rc=open_view(db,sql,C.byref(view))
        if rc:raise OSError('MSI view '+str(rc))
        rows=[]
        try:
            rc=execute(view,0)
            if rc:raise OSError('MSI execute '+str(rc))
            while True:
                record=handle();rc=fetch(view,C.byref(record))
                if rc==259:break
                if rc:raise OSError('MSI fetch '+str(rc))
                try:rows.append([field(record,i) for i in range(1,count+1)])
                finally:close(record)
        finally:close(view)
        return rows
    r=dict(status='unpacking',board_operations=False,MSI_installed=False,application_started=False,
           destination=str(dest),MSI_sha256=sha(source/'USART HMI.msi'),CAB_sha256=sha(source/'disk1.cab'))
    def save():(out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save();print(out,flush=True)
    try:
        files=query('SELECT `File`, `Component_`, `FileName`, `FileSize` FROM `File`',4)
        components=dict(query('SELECT `Component`, `Directory_` FROM `Component`',2))
        directories={row[0]:row[1:] for row in query('SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`',3)}
        properties=dict(query('SELECT `Property`, `Value` FROM `Property`',2))
        r['product']={key:properties.get(key) for key in ('ProductName','ProductVersion','Manufacturer')}
        (out/'MSI-tables.json').write_text(json.dumps(dict(files=files,components=components,directories=directories,
            product=r['product']),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raw=dest/'cab-raw';raw.mkdir()
        with (out/'expand.stdout').open('wb') as log:
            p=subprocess.run(['expand.exe','-F:*',str(source/'disk1.cab'),str(raw)],stdout=log,stderr=subprocess.STDOUT,timeout=90)
        if p.returncode:raise RuntimeError('Windows CAB expansion failed '+str(p.returncode))
        extracted={p.name.lower():p for p in raw.rglob('*') if p.is_file()}
        app=dest/'app';app.mkdir();cache={}
        def directory(key,seen=()):
            if key in cache:return cache[key]
            if key in seen:raise ValueError('MSI directory cycle')
            parent,name=directories[key]
            base=directory(parent,seen+(key,)) if parent else app
            name=name.split(':',1)[0].split('|')[-1]
            path=base if not parent or name in ('.','SourceDir','') else base/name
            if path.resolve()!=app.resolve() and app.resolve() not in path.resolve().parents:
                raise ValueError('MSI directory escapes E: destination')
            cache[key]=path;return path
        rows=[]
        for key,component,name,size in files:
            filename=name.split('|')[-1]
            if Path(filename).name!=filename or '/' in filename or '\\' in filename:raise ValueError('MSI filename')
            original=extracted.get(key.lower())
            if not original or original.stat().st_size!=int(size):raise ValueError('Missing or wrong-size CAB member '+key)
            target=directory(components[component])/filename;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(original,target)
            rows.append(dict(path=str(target.relative_to(app)),bytes=int(size),sha256=sha(target)))
        r.update(status='unpacked_P65_TJC_editor_files_to_E_without_MSI_install',files=len(rows),
                 application_root=str(app),executables=[str(p) for p in app.rglob('*.exe')])
        (out/'files-manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except Exception as e:r.update(status='failed_or_incomplete_editor_unpack',error=repr(e))
    finally:close(db)
    save();print(r['status']);print(r.get('application_root',''))
    return 0 if r['status'].startswith('unpacked_') else 1
if __name__=='__main__':raise SystemExit(main())
