def prepare_source(self, tx):
    require_tx_off(tx)
    source_path = ROOT / 'results/p75-plan-20261026T100342Z/2026102601/report.json'
    meta, payload, tar_sha = validate_source_package(source_path)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/pkg.gz':
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = None; worker = None
    if self.tx_transport != 'usb-console':
        server = http.server.ThreadingHTTPServer(('192.168.2.10', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
    try:
        with self.board('TX') as (b, identity):
            fresh = self.inspect('TX', b, identity)
            require_tx_off(fresh)
            if fresh['boot_id'] != tx['boot_id']:
                raise ValueError('TX boot changed before upload')
            self.record['resolved_RAM_tmp'] = board_ram_tmp(b)
            directory = '/tmp/p35-p59-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            b.command('d=' + directory); b.command('test ! -e $d')
            b.command('mkdir $d'); b.command('u=$d/pkg.gz')
            if self.tx_transport == 'usb-console':
                self.record['console_transfer'] = upload_uudecode(b, payload, directory + '/pkg.gz')
            else:
                b.command('h=http://192.168.2.10:' + str(server.server_port) + '/pkg.gz')
                b.command('wget -q -T 10 -O $u $h', timeout=15)
            if self.digest(b, directory + '/pkg.gz') != meta['archive_sha256']:
                raise ValueError('Transferred package SHA mismatch')
            if 'console_transfer' in self.record:
                self.record['console_transfer']['remote_SHA_verified_by_caller'] = True
            b.command('gzip -dc $d/pkg.gz >$d/pkg.tar')
            if self.digest(b, directory + '/pkg.tar') != tar_sha:
                raise ValueError('Tar SHA mismatch')
            b.command('tar -xf $d/pkg.tar -C $d'); b.command('chmod 755 $d/guard')
            b.command('cd $d'); b.command('sha256sum -c sums')
            for name, expected in meta['files_sha256'].items():
                if self.digest(b, directory + '/' + name) != expected:
                    raise ValueError('Extracted source SHA mismatch')
            inspection = b.command('./guard --inspect', timeout=15)
            expected = dict(tx0_sampling_frequency='30720000',
                tx0_hardwaregain='-10.000000 dB', tx0_rf_bandwidth='18000000',
                tx0_rf_port_select='A', tx_lo='2450000000', TX_DMA_sampling_frequency='30720000')
            for key, value in expected.items():
                if not re.search(r'^' + re.escape(key + '=' + value) + r'\r?$', inspection, re.M):
                    raise ValueError('TX RF/DMA differs: ' + key)
            for name in ('tone', 'bpsk', 'qpsk', 'qam16'):
                b.command('h=' + meta['files_sha256'][name])
                result = b.command('./guard --check ' + name + ' 131072 $h')
                if 'INPUT_CHECK_PASS samples=131072' not in result:
                    raise ValueError('Native file check failed')
            self.record['source'] = dict(expected_boot=tx['boot_id'],
                remote_directory=directory, files_sha256=meta['files_sha256'],
                source_report=source_path.relative_to(ROOT).as_posix(),
                source_report_sha256=sha(source_path), references=meta['references'],
                source_peak_component_counts=256, inspect=inspection)
            self.record['result'] = 'verified_frozen_sources_uploaded_RAM_only_no_TX'
    finally:
        if server:
            server.shutdown(); server.server_close()
        if worker:
            worker.join(timeout=3)
