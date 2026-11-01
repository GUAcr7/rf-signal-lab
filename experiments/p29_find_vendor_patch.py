"""Discover relocated patch attachment through the public vendor document API."""
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-vendor-patch-api-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    for i, endpoint in enumerate(['/api/khub/documents/search', '/api/khub/maps/search', '/api/khub/search']):
        url = 'https://docs.amd.com' + endpoint
        try:
            request = urllib.request.Request(url, json.dumps(dict(query='76960')).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read(2*1024*1024)
            (out / f'response{i}.json').write_bytes(data)
            obj = json.loads(data)
            print(endpoint, str(obj)[:2300])
        except urllib.error.HTTPError as error:
            body = error.read(2000).decode(errors='replace')
            (out / f'error{i}.txt').write_text(body, encoding='utf-8')
            print(endpoint, error.code, body[:120])
        except Exception as error:
            print(endpoint, type(error).__name__, str(error)[:160])
    print(out)
    maps_file = out / 'response1.json'
    if maps_file.exists():
        maps = json.loads(maps_file.read_text('utf-8'))['results']
        exact = next(m for m in maps if m['readerUrl'] == 'https://docs.amd.com/r/en-US/76960')
        for suffix in ['/attachments', '']:
            try:
                with urllib.request.urlopen(exact['mapUrl'] + suffix, timeout=15) as response:
                    data = response.read(2*1024*1024)
                (out / ('attachments.json' if suffix else 'map.json')).write_bytes(data)
                print(suffix or '/map', data.decode('utf-8')[:3300])
            except Exception as error:
                print(suffix, str(error)[:200])


if __name__ == '__main__':
    main()
