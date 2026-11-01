"""Archive relevant local primary timing pages without altering vendor files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pdfplumber

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
    'ad9361':Path('D:/AD9361/AD9361/开发参考资料/AD9361.pdf'),
    'interface':Path('D:/AD9361/AD9361/开发参考资料/AD9361 Interface Spec v2.5.pdf'),
    'panel_module':Path('D:/xilinx/xilinx/1-开箱必读/产品规格书/拓展模块规格书/TL070A显示屏规格书.pdf'),
}


def main():
    out=ROOT/'results'/('p31-timing-sources-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='extracted_for_review',board_operations=False,sources={})
    for name,path in SOURCES.items():
        folder=out/name;folder.mkdir()
        pages=[]
        with pdfplumber.open(path) as pdf:
            for number,page in enumerate(pdf.pages,1):
                text=page.extract_text() or ''
                (folder/f'page-{number:02d}.txt').write_text(text,encoding='utf-8')
                terms=[word for word in ['LVDS TIMING','Setup Time','Hold Time','DATA_CLK','FB_CLK','setup time','hold time','TTL','Timing','TL-70'] if word in text]
                pages.append(dict(page=number,hits=terms))
            selected=[p['page'] for p in pages if 'LVDS TIMING' in p['hits'] or 'Setup Time' in p['hits'] or 'Hold Time' in p['hits']]
            if name=='ad9361':selected=[7]
            if name=='interface':selected=[20,21,22,29]
            if name=='panel_module':selected=list(range(1,len(pages)+1))
            for number in selected:
                pdf.pages[number-1].to_image(width=1900).save(folder/f'page-{number:02d}.png')
        report['sources'][name]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pages=pages,rendered=selected)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)
    for name,item in report['sources'].items():print(name,[(p['page'],p['hits']) for p in item['pages'] if p['hits']])


if __name__=='__main__':main()
