"""Render the design manifest, not a compiled or downloadable screen image."""
from datetime import datetime,timezone
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]

def main():
    config=json.loads((ROOT/'configs/tjc-source-page.json').read_text())
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p63-page-preview-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    fontpath=Path('C:/Windows/Fonts/segoeui.ttf')
    font=lambda size:ImageFont.truetype(str(fontpath),size)
    images=[]
    for mode in ('offline','ready','running'):
        im=Image.new('RGB',(480,272),'#111b2c');d=ImageDraw.Draw(im)
        def text(pos,value,size=14,fill='#e9eff9'):d.text(pos,value,font=font(size),fill=fill)
        text((12,7),'RF SOURCE',20)
        state={'offline':'OFFLINE','ready':'READY','running':'RUNNING'}[mode]
        d.rounded_rectangle((310,8,468,32),6,fill='#23344a');text((322,9),state,15,'#8cd6f7')
        for item in config['creation_order_buttons_first']:
            x,y,w,h=item['rect'];selected=item['id']==1
            color='#1e708c' if selected else '#29394e'
            if item['id']==7:color='#ad3544'
            if item['id']==6:color='#287a60' if mode=='ready' else '#354151'
            d.rounded_rectangle((x,y,x+w,y+h),5,fill=color)
            box=d.textbbox((0,0),item['text'],font=font(16))
            text((x+(w-(box[2]-box[0]))/2,y+(h-22)/2),item['text'],16)
        suffix={'offline':'not applied','ready':'applied','running':'active'}[mode]
        text((12,94),'Selected: TONE  |  '+suffix,15)
        d.rounded_rectangle((12,122,468,169),5,fill='#1b2a40')
        text((22,126),'LO 2450 MHz     Offset +960 kHz',14)
        text((22,146),'Fs 30.72 MS/s     TX gain -10 dB',14)
        text((12,184),'Duration (s)',14)
        d.rounded_rectangle((188,180,288,212),5,fill='#1b2a40');text((226,181),'15',19)
        text((350,185),'8 - 60 s',13,'#a6bbd4')
        path=out/(mode+'.png');im.save(path);images.append(path.name)
    (out/'report.json').write_text(json.dumps(dict(status='P63_design_preview_only',
        size=[480,272],images=images,compiled_HMI=False,downloaded_to_screen=False),indent=2)+'\n')
    print(out/'report.json')

if __name__=='__main__':main()
