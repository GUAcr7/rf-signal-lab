"""Archive supplied official TJC documentation using HTTP, with byte hashes.

This fetches documentation only. It never opens a UART or downloads screen firmware.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class TextAndLinks(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.links = []; self.ignored = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.ignored += 1
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'li', 'tr', 'br'):
            self.parts.append('\n')
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignored = max(0, self.ignored - 1)
    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', action='append', default=[], help='name=official-document-URL')
    args = parser.parse_args()
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p61-tjc-docs-%Y%m%dT%H%M%SZ')
    out.mkdir()
    urls = {
        'index': 'http://wiki.tjc1688.com/',
        'serial-download': 'http://wiki.tjc1688.com/start/create_project/create_project_9.html',
        'SD-download': 'http://wiki.tjc1688.com/start/create_project/create_project_10.html',
        'video': 'http://wiki2.tjc1688.com/video.html',
        'T1-product': 'https://www.tjc1688.com/contents/7/13.html',
        'T1-structure': 'https://www.tjc1688.com/contents/25/75.html',
    }
    if args.url:
        urls = dict(item.split('=', 1) for item in args.url)
        if any(not name.replace('-', '').isalnum() for name in urls):
            raise ValueError('Use simple document names')
        if any(urllib.parse.urlparse(url).hostname not in ('wiki.tjc1688.com', 'wiki2.tjc1688.com', 'www.tjc1688.com') for url in urls.values()):
            raise ValueError('Only official TJC domains')
    def fetch(item):
        name, url = item
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError('Document size bound exceeded')
                final_url = response.url
            (out / (name + '.html')).write_bytes(raw)
            text = raw.decode('utf-8-sig')
            parser = TextAndLinks(); parser.feed(text)
            plain = '\n'.join(s.strip() for s in ''.join(parser.parts).splitlines() if s.strip())
            (out / (name + '.txt')).write_text(plain + '\n', encoding='utf-8')
            links = sorted(set(urllib.parse.urljoin(final_url, href) for href in parser.links))
            return name, dict(status='fetched', url=url, final_url=final_url,
                bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), links=links)
        except Exception as error:
            return name, dict(status='failed', url=url, error=repr(error))
    with ThreadPoolExecutor(max_workers=4) as workers:
        records = dict(workers.map(fetch, urls.items()))
    report = dict(status='official_docs_fetched_model_and_hardware_not_confirmed',
        board_operations=False, screen_model=None, firmware_downloaded=False, pages=records,
        web_reader_note='HTTPS web-reader requests timed out/502; supplied HTTP documentation worked using urllib.')
    (out / 'executed.py').write_bytes(Path(__file__).read_bytes())
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out)
    for name, item in records.items():
        print(name, item['status'])
    print('Relevant official links:')
    for name, item in records.items():
        relevant = [link for link in item.get('links', []) if any(word in link.lower()
                    for word in ('instruction', 'command', 'return', 'usart', 'model', 'download', 'select', 'serial', 'data'))]
        for link in relevant[:15]:
            print(name, link)
        if len(relevant) > 15:
            print(name, str(len(relevant)) + ' links recorded; showing first 15')


if __name__ == '__main__':
    main()
