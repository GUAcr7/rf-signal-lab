"""Retain the official patch page HTML and identify its vendor attachment/API links."""
from datetime import datetime, timezone
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-patch-page-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    for i, url in enumerate(['https://docs.amd.com/r/en-US/76960/Solution',
                              'https://adaptivesupport.amd.com/s/article/76960?language=en_US']):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read(5*1024*1024)
            (out / f'page{i}.html').write_bytes(data)
            text = data.decode('utf-8', errors='replace')
            print(url, 'bytes', len(data))
            for pattern in [r'<meta[^>]+>', r'.{0,100}y2k22.{0,150}', r'.{0,70}(?:attachment|documentId|document_id|khub|mapId).{0,120}']:
                for match in re.findall(pattern, text, re.I)[:18]:
                    print(match)
        except Exception as error:
            print(type(error).__name__, str(error)[:200])
    print(out)


if __name__ == '__main__':
    main()
