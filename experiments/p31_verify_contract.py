"""Independently compare compiled DT properties with the saved Vivado graph."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from p30_display_profile import properties

ROOT=Path(__file__).resolve().parents[1]


def inspect(bd,p):
    checks=[]
    def check(name,condition,detail=None):checks.append(dict(check=name,passed=bool(condition),detail=detail))
    def cells(path):return p[path]['u32']
    def wires(pin):return [name for name,net in bd['nets'].items() if pin in net['ports']]
    def joins(pins):
        nets=[wires(pin) for pin in pins]
        return all(len(n)==1 for n in nets) and len({n[0] for n in nets})==1
    clock=cells('/amba/slcr@f8000000/clkc@100/phandle')[0]
    def clock_index(pin):
        match=[15+i for i in range(4) if joins([pin,f'sys_ps7/FCLK_CLK{i}'])]
        if len(match)!=1:raise RuntimeError('unknown or ambiguous actual clock '+pin)
        return match[0]
    def clock_property(node,pins):
        expected=[v for pin in pins for v in (clock,clock_index(pin))]
        actual=cells(node+'/clocks');check('actual clock wiring '+node,actual==expected,dict(actual=actual,expected=expected))
    for address,ip in [('7c400000','axi_ad9361_adc_dma'),('7c420000','axi_ad9361_dac_dma')]:
        clock_property('/amba/dma@'+address,[ip+'/s_axi_aclk'])
    clock_property('/amba/clk_wiz@43c10000',['clk_wiz_0/clk_in1','clk_wiz_0/s_axi_aclk'])
    clock_property('/amba/dma@43000000',['axi_vdma_0/s_axi_lite_aclk','axi_vdma_0/m_axi_mm2s_aclk',
        'axi_vdma_0/m_axis_mm2s_aclk','axi_vdma_0/m_axi_s2mm_aclk','axi_vdma_0/s_axis_s2mm_aclk'])
    ps=bd['components']['sys_ps7']['parameters']
    for index,wanted in [(0,100.0),(1,200.0)]:
        actual=float(ps[f'PCW_ACT_FPGA{index}_PERIPHERAL_FREQMHZ']['value'])
        check('PS FCLK'+str(index)+' declared rate',abs(actual-wanted)<.001,actual)
    check('PS interrupt order retained',ps['PCW_IRQ_F2P_MODE']['value']=='REVERSE')
    irq_nodes={'/amba/dma@7c400000':('axi_ad9361_adc_dma/irq',[13]),
        '/amba/dma@7c420000':('axi_ad9361_dac_dma/irq',[12]),
        '/amba/dma@43000000':('axi_vdma_0/mm2s_introut',[0,1]),
        '/amba/v_tc@43c20000':('v_tc_0/irq',[2])}
    for node,(pin,indices) in irq_nodes.items():
        actual=cells(node+'/interrupts')
        expected_ids=[29+i if i<8 else 44+i for i in indices]
        check('GIC SPI IDs '+node,actual[1::3]==expected_ids,dict(actual=actual[1::3],expected=expected_ids))
        check('IRQ wire '+node,joins([pin,f'sys_concat_intc/In{indices[0]}']))
    check('VDMA write IRQ wire',joins(['axi_vdma_0/s2mm_introut','sys_concat_intc/In1']))
    segments=bd['addressing']['/sys_ps7']['address_spaces']['Data']['segments']
    windows={}
    for seg in segments.values():
        scale={'K':1024,'M':1024**2,'G':1024**3}[seg['range'][-1]]
        windows[seg['address_block']]=(int(seg['offset'],0),int(seg['range'][:-1])*scale)
    allocations={
        '/amba/dma@7c400000':'/axi_ad9361_adc_dma/s_axi/axi_lite',
        '/amba/dma@7c420000':'/axi_ad9361_dac_dma/s_axi/axi_lite',
        '/amba/dma@43000000':'/axi_vdma_0/S_AXI_LITE/Reg',
        '/amba/clk_wiz@43c10000':'/clk_wiz_0/s_axi_lite/Reg',
        '/amba/v_tc@43c20000':'/v_tc_0/ctrl/Reg',
        '/amba/cf-ad9361-lpc@79020000':'/axi_ad9361/s_axi/axi_lite',
        '/amba/cf-ad9361-dds-core-lpc@79024000':'/axi_ad9361/s_axi/axi_lite'}
    for node,block in allocations.items():
        start,size=cells(node+'/reg');base,span=windows[block]
        check('register resource inside decoded IP '+node,base<=start and start+size<=base+span,
            dict(DT=[start,size],hardware=[base,span]))
    gpio=cells('/amba/gpio@e000a000/phandle')[0]
    phy='/amba/spi@e0007000/ad9361-phy@0'
    for attribute,emio in [('en_agc-gpios',44),('sync-gpios',45),('reset-gpios',46),('enable-gpios',47),('txnrx-gpios',48)]:
        check('RF GPIO mapping '+attribute,cells(phy+'/'+attribute)==[gpio,54+emio,0])
    check('touch EMIO0 number',cells('/amba/spi@e0006000/ads7846@0/pendown-gpio')==[gpio,54,0])
    check('touch IRQ EMIO0 number',cells('/amba/spi@e0006000/ads7846@0/interrupts')[0]==54)
    return checks


def main():
    active=json.loads((ROOT/'results/p31-overlay-active.json').read_text('utf-8'))
    origin=Path(active['report']);report=json.loads(origin.read_text('utf-8'))
    work=Path(json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))['work'])
    bdpath=work/'project/combined.srcs/sources_1/bd/system/system.bd'
    bd=json.loads(bdpath.read_text('utf-8'))['design']
    dtb=origin.parent/'offline-combined-base.dtb';p=properties(dtb.read_bytes())
    out=ROOT/'results'/('p31-contract-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    checks=inspect(bd,p);negative=[]
    for name,key,wrong in [
        ('stale factory DMA clock','/amba/dma@7c400000/clocks',[p['/amba/slcr@f8000000/clkc@100/phandle']['u32'][0],16]),
        ('wrong RF interrupt','/amba/dma@7c420000/interrupts',[0,29,0]),
        ('oversized DMA resource','/amba/dma@7c400000/reg',[0x7c400000,65536]),
        ('wrong touch EMIO','/amba/spi@e0006000/ads7846@0/interrupts',[55,0])]:
        broken=deepcopy(p);broken[key]['u32']=wrong
        failures=[c['check'] for c in inspect(bd,broken) if not c['passed']]
        negative.append(dict(fixture=name,detected=bool(failures),failures=failures))
    result=dict(status='passed' if all(c['passed'] for c in checks) and all(n['detected'] for n in negative) else 'failed',
        created_utc=datetime.now(timezone.utc).isoformat(),overlay_report=str(origin),bd=str(bdpath),
        bd_sha256=hashlib.sha256(bdpath.read_bytes()).hexdigest(),dtb_sha256=hashlib.sha256(dtb.read_bytes()).hexdigest(),
        checks=checks,negative_fixtures=negative,board_operations=False,
        limitations=['Target driver/binding and hardware not validated','ADC and DDS share one RF IP register window; their historical subrange overlap is intentional and retained',
            'TPG control window and IRQ In3 have no Linux driver node in the inherited DRM path; unused by basic framebuffer display',
            'TTC PWM ownership and VDMA legacy clock-name compatibility remain runtime gates'])
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(out);print(result['status'],len(checks),len(negative))
    for c in checks:
        if not c['passed']:print(c)
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
