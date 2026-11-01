"""Quarantine the old deployment instructions; retain bytes and verify raw format.

Creates investigation artifacts only, never installs any package on a board.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from rfsig.bitstream_format import extract_bit_payload,validate_raw_sync
from p32_session import ROOT

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    old=ROOT/'results/p34-deploy-package'
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-package-format-audit-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    original=old/'rf-display-p32.bin'
    source=original.read_bytes()
    parsed=extract_bit_payload(source)
    native=Path('E:/FPGA_Tools/Work/p34-binfile-20261020/rf_display_top.bin')
    raw=native.read_bytes()
    validate_raw_sync(raw)
    if parsed.data!=raw:raise RuntimeError('extracted and native raw payload differ')
    (out/'p34-README.before.md').write_bytes((old/'README.md').read_bytes())
    legacy=ROOT/'board/boot/p32-deploy.sh'
    (out/'p32-deploy.before.sh').write_bytes(legacy.read_bytes())
    (out/'rf-display-p32.raw.bin').write_bytes(raw)
    warning='''# P34 旧部署包已停用（P35审查）

禁止使用此目录部署。原始二进制仅为保留实验依据，未覆盖或删除。

- `rf-display-p32.bin` 实际是带元数据头的 `.bit` 容器，不能按本项目裸配置文件使用。
- 配套合并 overlay 曾使启动失去响应，原因尚未确诊；两种厂家树分别 probe 成功不等于并行验收。
- 禁止热卸载 RF overlay/PWM 驱动；原说明的 `rmdir` 回滚已撤销。
- 原包还保留148.5MHz初始像素时钟和辅助LVDS支路，不是新TTL33候选。

正确格式副本已独立与Vivado原生 `.bin` 逐字节比对，但只用于调查，仍不允许部署。
新启动试验必须先核验厂家文件、启动保护、实际bitstream/DT配对，并保存完整启动日志。
失败后使用预设的下一次正常重启恢复路径；若串口也无响应，再按实测U-Boot恢复办法处理。

最新状态从项目 `START-HERE.md` 恢复。旧说明完整副本与本次格式报告在：
'''+str(out.relative_to(ROOT))+'\n'
    (old/'README.md').write_text(warning,encoding='utf-8',newline='\n')
    block='''# P35: retired after reproducible package-format and deployment audit.
echo "RETIRED: P32 deployment is blocked; read START-HERE.md and P35 records" >&2
exit 3

'''
    text=legacy.read_text('utf-8')
    if 'P35: retired' not in text:
        if not text.startswith('#!/bin/sh\n'):raise RuntimeError('unexpected legacy deploy script')
        legacy.write_text('#!/bin/sh\n'+block+text[len('#!/bin/sh\n'):],encoding='utf-8',newline='\n')
    report=dict(status='legacy_deployment_blocked_raw_format_verified_not_deployable',
        board_operations=False,old_container=str(original),old_container_sha256=sha(source),
        old_container_bytes=len(source),parsed_header_offset=parsed.offset,metadata=parsed.fields,
        native_bin=str(native),native_bin_sha256=sha(raw),native_bin_bytes=len(raw),
        extracted_equals_native=True,artifact=str(out/'rf-display-p32.raw.bin'),
        overlay_validated_on_hardware=False,CDC_closed=False,external_timing_closed=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (old/'DEPLOYMENT-BLOCKED.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status'])

if __name__=='__main__':main()
