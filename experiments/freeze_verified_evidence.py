"""Freeze current project sources and hash already-verified experimental evidence."""
from pathlib import Path
import argparse,json,hashlib,re,shutil

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('evidence',type=Path);a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.evidence.resolve();out.relative_to(root/'results');assert out.is_dir()
    snapshot=out/'source-snapshot';snapshot.mkdir()
    files=[root/'README.md',root/'docs/implementation-guide.md',root/'docs/experiments/EXP-P06.md',root/'docs/models/CNN-115-SYNTHETIC-v1.md']+list((root/'docs/experiments').glob('*20261011.md'))
    for pattern in ['p06*','p07b*','p08*','p09*','p10*','serve_one_file.py','freeze_verified_evidence.py']:files+=list((root/'experiments').glob(pattern))
    for name in ['tiny_cnn_probe.py','synthetic_dataset.py','modulation_baseline.py','trainable_cnn.py','cnn_quantization.py']:files.append(root/'src/rfsig'/name)
    for pattern in ['test_tiny_cnn*','test_synthetic_dataset*','test_modulation_baseline*','test_trainable_cnn*','test_cnn_quantization*']:files+=list((root/'tests').glob(pattern))
    for part in ['tiny_cnn_probe','arm_rx_probe','modulation_baseline']:files+=list((root/'embedded'/part).glob('*.c'))
    files+=list((root/'fpga/vendor-baseline').glob('reimplement-*.tcl'))
    source=[]
    for f in sorted(set(files)):
        if not f.is_file():continue
        rel=f.relative_to(root);dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest);source.append({'path':rel.as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)});assert sha(dest)==source[-1]['sha256']
    (out/'source-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
    archives=[]
    for path in ['p10-baseline-arm-20261011T054505Z','p10-trained-cnn-20261011T055826Z','p07b-arm-spectrum-20261011T060307Z']:
        d=root/'results'/path;r=json.loads((d/'report.json').read_text());archive=Path(r['archive']);assert sha(archive)==r['sha256'];bundle=d/r['prefix'];count=0
        for line in (bundle/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1);assert sha(bundle/name)==digest;count+=1
        archives.append({'path':archive.relative_to(root).as_posix(),'sha256':r['sha256'],'inner_files_verified':count})
    dataset=root/'data/p08-synthetic-v1-20261011T053828Z';m=json.loads((dataset/'manifest.json').read_text());v=json.loads((dataset/'verification.json').read_text());assert sha(dataset/'manifest.json')==v['manifest_sha256']
    for r in m['records']:assert sha(dataset/r['file'])==r['file_sha256']
    fresh=root/'results/p10-trained-cnn-20261011T055826Z/fresh-holdout';fm=json.loads((fresh/'manifest.json').read_text())
    for r in fm['records']:assert sha(fresh/r['file'])==r['file_sha256']
    returns=[]
    for path in ['p06-arm-board-readback-20261011-131559','p06-cnn-board-readback-20261011-132815','p06-native-rx-readback-20261011-133251','p10-baseline-readback-20261011-135200','p10-cnn-readback-20261011-140055','p07b-spectrum-readback-20261011-140500']:
        d=root/'results'/path;r=json.loads((d/'report.json').read_text(encoding='utf-8-sig'));archive=d/'board-results.tar.gz';assert sha(archive)==r['archive_sha256'];returns.append({'path':archive.relative_to(root).as_posix(),'sha256':r['archive_sha256'],'bytes':archive.stat().st_size})
    links=[]
    for f in files:
        if f.suffix!='.md':continue
        for target in re.findall(r'\]\(([^)]+)\)',f.read_text(encoding='utf-8-sig')):
            if '://' in target or target.startswith(('#','mailto:')):continue
            path=target.split('#',1)[0]
            if path and not (f.parent/path).exists():links.append({'file':f.relative_to(root).as_posix(),'missing':path})
    digest=sha(root/'.git/index');assert digest=='8ead9f45d19caee3dca3792831bc4856801334a17a87c00e6080834572cbc83d'
    result={'status':'verified_archives_datasets_readbacks_source_snapshots_index','source_files_snapshotted':len(source),'dataset_records_hashed':len(m['records']),'fresh_holdout_records_hashed':len(fm['records']),'prepared_archives':archives,'retrieved_archives':returns,'index_sha256':digest,'markdown_missing_local_targets':links,'hardware_rerun':False,'staged_or_committed':False}
    (out/'artifact-ledger.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
