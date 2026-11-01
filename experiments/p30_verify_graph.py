"""Independently inspect saved BD, generated HDL and source integrity gates."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))
    preparation=json.loads(Path(active['preparation']).read_text('utf-8'))
    work=Path(active['work'])
    path=work/'project/combined.srcs/sources_1/bd/system/system.bd'
    bd=json.loads(path.read_text('utf-8'))['design']
    out=ROOT/'results'/('p30-graph-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',created_utc=datetime.now(timezone.utc).isoformat(),bd=str(path),bd_sha256=sha(path),checks=[],board_operations=False)
    def check(label,condition,detail=None):
        report['checks'].append(dict(check=label,passed=bool(condition),detail=detail))
    def net_for(pin,interface=False):
        mapping=bd['interface_nets' if interface else 'nets']
        return [name for name,net in mapping.items() if pin in net['interface_ports' if interface else 'ports']]
    def joined(label,pins,interface=False):
        names=[net_for(pin,interface) for pin in pins]
        check(label,all(len(n)==1 for n in names) and len({n[0] for n in names if n})==1,dict(zip(pins,names)))
    ps=[name for name,c in bd['components'].items() if 'processing_system7' in c.get('vlnv','')]
    check('exactly one PS7',ps==['sys_ps7'],ps)
    check('ClockWiz uses internal PS clock without primary-clock redefinition',
        bd['components']['clk_wiz_0']['parameters'].get('PRIM_SOURCE',{}).get('value')=='No_buffer')
    params=bd['components']['sys_ps7']['parameters']
    for key,value in {'PCW_GPIO_EMIO_GPIO_WIDTH':'64','PCW_SPI1_SPI1_IO':'EMIO','PCW_IRQ_F2P_MODE':'REVERSE',
            'PCW_UART1_UART1_IO':'MIO 12 .. 13','PCW_MIO_8_IOTYPE':'LVCMOS 3.3V'}.items():
        actual=params.get(key,{}).get('value')
        check('PS '+key,actual==value,actual)
    for i in range(4):
        joined(f'video M0{i} clock',['sys_ps7/FCLK_CLK1',f'axi_cpu_interconnect/M0{i}_ACLK'])
        joined(f'video M0{i} reset',['rst_ps7_0_200M/peripheral_aresetn',f'axi_cpu_interconnect/M0{i}_ARESETN'])
    joined('RF 100 MHz domain',['sys_ps7/FCLK_CLK0','sys_ps7/M_AXI_GP0_ACLK','sys_ps7/S_AXI_HP1_ACLK','sys_ps7/S_AXI_HP2_ACLK','axi_ad9361/s_axi_aclk'])
    joined('video DDR 200 MHz domain',['sys_ps7/FCLK_CLK1','sys_ps7/S_AXI_HP0_ACLK','smartconnect_0/aclk','axi_vdma_0/m_axi_mm2s_aclk','axi_vdma_0/m_axi_s2mm_aclk'])
    joined('RF receive DMA HP1',['axi_ad9361_adc_dma/m_dest_axi','axi_hp1_interconnect/S00_AXI'],True)
    joined('RF transmit DMA HP2',['axi_ad9361_dac_dma/m_src_axi','axi_hp2_interconnect/S00_AXI'],True)
    joined('video HP0',['smartconnect_0/M00_AXI','sys_ps7/S_AXI_HP0'],True)
    for endpoint,index in {'axi_vdma_0/mm2s_introut':0,'axi_vdma_0/s2mm_introut':1,'v_tc_0/irq':2,'v_tpg_0/interrupt':3,'axi_ad9361_dac_dma/irq':12,'axi_ad9361_adc_dma/irq':13}.items():
        joined(f'IRQ {index}',[endpoint,f'sys_concat_intc/In{index}'])
    for index in [4,5,6,7,8,9,10,11,14,15]:
        joined(f'unused IRQ {index} tied low',['integration_zero/dout',f'sys_concat_intc/In{index}'])
    joined('touch SPI select input high',['integration_one/dout','sys_ps7/SPI0_SS_I'])
    expected={'/axi_ad9361/s_axi/axi_lite':0x79020000,'/axi_ad9361_adc_dma/s_axi/axi_lite':0x7c400000,
        '/axi_ad9361_dac_dma/s_axi/axi_lite':0x7c420000,'/axi_vdma_0/S_AXI_LITE/Reg':0x43000000,
        '/clk_wiz_0/s_axi_lite/Reg':0x43c10000,'/v_tc_0/ctrl/Reg':0x43c20000,'/v_tpg_0/s_axi_CTRL/Reg':0x43c00000}
    segments=bd['addressing']['/sys_ps7']['address_spaces']['Data']['segments']
    actual={seg['address_block']:int(seg['offset'],0) for seg in segments.values()}
    check('seven preserved peripheral windows',actual==expected,actual)
    ranges=[]
    for seg in segments.values():
        size=int(seg['range'][:-1])*{'K':1024,'M':1024**2,'G':1024**3}[seg['range'][-1]]
        start=int(seg['offset'],0);ranges.append((start,start+size,seg['address_block']))
    ranges.sort()
    check('no overlapping CPU peripheral windows',all(a[1]<=b[0] for a,b in zip(ranges,ranges[1:])),ranges)
    annotation_names={Path(a['path']).name for a in preparation['interface_annotations']}
    correction_path=ROOT/'results/p30-xdc-correction.json'
    correction=json.loads(correction_path.read_text('utf-8')) if correction_path.exists() else None
    for item in preparation['inputs']:
        source=Path(item['source']);target=Path(item['target'])
        if correction and str(target)==correction['target']:
            check('reviewed XDC correction source',sha(source)==correction['after_sha256'])
            check('reviewed XDC correction copy',sha(target)==correction['after_sha256'])
            continue
        check('source unchanged '+source.name,sha(source)==item['sha256'])
        if target.name in annotation_names:
            restored=target.read_text('utf-8').replace('    (* X_INTERFACE_IGNORE = "true" *)\n','')
            check('metadata-only HDL '+target.name,restored==source.read_text('utf-8'))
        else:check('copy unchanged '+target.name,sha(target)==item['sha256'])
    generated=work/'project/combined.gen/sources_1/bd/system/synth/system.v'
    text=generated.read_text('utf-8')
    report['generated_hdl']=dict(path=str(generated),sha256=sha(generated))
    check('VTC adaptive sync input tied low',".sof_state(1'b0)" in text)
    check('VTC fsync input tied low',".fsync_in(1'b0)" in text)
    check('TPG progressive field tied low','.fid_in(integration_zero_dout)' in text)
    check('video out progressive field tied low','.fid(integration_zero_dout)' in text)
    report['status']='passed' if all(c['passed'] for c in report['checks']) else 'failed'
    report['limitations']=['Saved structure only, not dynamic AXI transactions','No board/PS-init/CDC/IO timing acceptance','RF DMA device-tree window size remains a separate review item']
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status'],len(report['checks']))
    for check in report['checks']:
        if not check['passed']:print(check)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
