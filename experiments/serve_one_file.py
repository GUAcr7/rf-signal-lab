"""Time-bounded one-file HTTP download for the identified USB-connected board."""
import argparse
import hashlib
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('file',type=Path); p.add_argument('events',type=Path)
    p.add_argument('--sha256',required=True)
    args=p.parse_args()
    data=args.file.read_bytes()
    assert hashlib.sha256(data).hexdigest()==args.sha256
    def event(item):
        item['time']=time.time()
        with args.events.open('a',encoding='utf-8') as f: f.write(json.dumps(item)+'\n')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self):
            self.connection.settimeout(10)
            if self.client_address[0]!='192.168.2.1': self.send_error(403); return
            if self.path!='/'+args.file.name: self.send_error(404); return
            self.send_response(200); self.send_header('Content-Length',str(len(data))); self.end_headers()
            try:
                self.wfile.write(data); self.wfile.flush()
                event({'event':'sent','bytes':len(data),'sha256':args.sha256})
                self.server.sent=True
            except OSError as e: event({'event':'error','error':str(e)})
    with HTTPServer(('192.168.2.10',8765),Handler) as server:
        server.timeout=1; server.sent=False
        event({'event':'ready','filename':args.file.name,'peer':'192.168.2.1','writes':False})
        print('READY '+args.file.name,flush=True)
        deadline=time.monotonic()+600
        while not server.sent and time.monotonic()<deadline: server.handle_request()
        event({'event':'stopped','reason':'sent' if server.sent else 'timeout'})

if __name__=='__main__': main()
