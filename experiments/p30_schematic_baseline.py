"""Extract carrier schematic evidence read-only; never infer core voltage from MIO."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pdfplumber

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=Path('D:/xilinx/xilinx/5-硬件资料/评估底板原理图/TLZ7xH-EVM评估底板原理图/TLZ7xH-EVM-B2原理图.pdf')
    out=ROOT/'results'/('p30-schematic-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    pages=[]
    with pdfplumber.open(source) as pdf:
        for index,page in enumerate(pdf.pages):
            text=page.extract_text() or ''
            (out/f'page-{index+1:02d}.txt').write_text(text,encoding='utf-8')
            hits=[term for term in ['UART1','MIO12','MIO_12','FAN','XPT2046','P15_LCD','Debug_UART','UART_RXD'] if term in text]
            pages.append(dict(page=index+1,hits=hits))
        # Sheet order is verified in the extracted page titles, not assumed to
        # match named PDF page labels. Retain complete relevant sheets.
        render=[n for n,p in enumerate(pages) if p['hits']]
        for index in render:
            pdf.pages[index].to_image(width=2400).save(out/f'page-{index+1:02d}.png')
    report=dict(status='extracted_for_review',source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),pages=pages,
        limitations=['Carrier schematic only; core-module PS DDR/voltage settings require matching core schematic','No board operations'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(json.dumps([p for p in pages if p['hits']],indent=2))


if __name__=='__main__':main()
