"""Finite offline learning viewer; explicit known labels, no board/AI access."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import numpy as np
if __package__:
    from .data_api import load_kit
else:
    from data_api import load_kit
from rfsig.replay_analysis import OfflineReplay,save_replay_snapshot


class LearningView:
    def __init__(self,records,directory,interactive=False,output_root=None):
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from matplotlib.widgets import Button,RadioButtons,Slider,CheckButtons
        names={f.name for f in font_manager.fontManager.ttflist}
        font=next((x for x in ('Microsoft YaHei','SimHei','Noto Sans CJK SC') if x in names),None)
        self.chinese=font is not None
        if font:plt.rcParams['font.family']=font
        plt.rcParams['axes.unicode_minus']=False
        self.records=records;self.directory=Path(directory);self.interactive=interactive
        self.output_root=Path(output_root) if output_root else self.directory/'exports'
        self.key='bpsk';self.block=0;self.full_band=False;self.last_export=None
        self.fig=plt.figure(figsize=(13.8,8.6))
        self.fig.canvas.manager.set_window_title('RF learning kit - SAVED REAL RF - OFFLINE')
        grid=self.fig.add_gridspec(2,2,left=.065,right=.91,bottom=.30,top=.835,wspace=.29,hspace=.46)
        self.time_ax=self.fig.add_subplot(grid[0,0]);self.info_ax=self.fig.add_subplot(grid[0,1])
        self.spec_ax=self.fig.add_subplot(grid[1,0]);self.water_ax=self.fig.add_subplot(grid[1,1])
        self.color_ax=self.fig.add_axes((.925,.30,.014,.215))
        self.fig.suptitle(self.text('真实射频记录 · 离线回放','SAVED REAL RF | OFFLINE FILE REPLAY'),y=.978,fontsize=17,fontweight='bold')
        self.label_text=self.fig.text(.065,.918,'',fontsize=11)
        self.fig.text(.065,.874,self.text('不连接板卡。播放速度与采样时钟无关；跨采集块的间隔未知。',
            'No hardware connection. Playback speed is independent of sample time. Inter-DMA gaps unknown.'),fontsize=10)
        self.status_text=self.fig.text(.065,.025,'',fontsize=10)
        self.feedback_text=self.fig.text(.36,.057,'',fontsize=9)
        self.selector=RadioButtons(self.fig.add_axes((.065,.082,.23,.16)),[records[k].label for k in records],active=list(records).index(self.key))
        self.selector.on_clicked(self.select_label)
        self.slider=Slider(self.fig.add_axes((.46,.223,.39,.025)),self.text('采集块','DMA block'),1,4,valinit=1,valstep=1)
        self.slider.on_changed(self.select_block)
        self.check=CheckButtons(self.fig.add_axes((.36,.16,.21,.04)),[self.text('显示全频段','Show full band')],[False])
        self.check.on_clicked(self.toggle_band)
        self.buttons=[]
        for left,label,callback in ((.36,self.text('开始 / 暂停','Start / Pause'),self.toggle),
                                     (.55,self.text('重新播放','Reset'),self.reset),
                                     (.74,self.text('保存当前画面','Export snapshot'),self.export)):
            b=Button(self.fig.add_axes((left,.085,.17,.055)),label);b.on_clicked(callback);self.buttons.append(b)
        self.timer=self.fig.canvas.new_timer(interval=100);self.timer.add_callback(self.step)
        self.fig.canvas.mpl_connect('close_event',lambda event:self.timer.stop())
        self.new_replay();self.draw()

    def text(self,cn,en):return cn if self.chinese else en

    def new_replay(self):
        self.timer.stop();record=self.records[self.key];x=record.iq[self.block]
        self.feedback_text.set_text('')
        power=float(np.mean(abs(x.astype(np.complex128))**2))
        self.replay=OfflineReplay(x,record.metadata['sample_rate_hz'],1024,1024,(-9e6,9e6),power,
            rf_lo_hz=record.metadata['rx_lo_hz'],max_rows=64)

    def select_label(self,label):
        self.key=next(k for k,v in self.records.items() if v.label==label)
        self.new_replay();self.draw()

    def select_block(self,value):
        self.block=int(value)-1;self.new_replay();self.draw()

    def toggle_band(self,_=None):
        self.full_band=not self.full_band;self.draw()

    def toggle(self,_=None):
        if self.replay.state=='running':self.replay.pause();self.timer.stop()
        elif self.replay.state!='finished':
            self.replay.start()
            if self.interactive:self.timer.start()
        self.draw()

    def step(self):
        frame=self.replay.advance()
        if frame is not None:self.draw()
        if self.replay.state!='running':self.timer.stop()
        # Matplotlib removes callbacks whose return compares equal to zero.
        return True

    def reset(self,_=None):
        self.timer.stop();self.replay.reset();self.feedback_text.set_text('');self.draw()

    def draw(self):
        r=self.replay;record=self.records[self.key];frame=r.latest
        for ax in (self.time_ax,self.info_ax,self.spec_ax,self.water_ax,self.color_ax):ax.clear()
        self.info_ax.axis('off');self.color_ax.set_visible(frame is not None)
        self.label_text.set_text(self.text(f'已知发送标签：{record.label}（不是AI识别结果）  |  采集块 {self.block+1}/4',
            f'Known TX label: {record.label} (not an AI prediction) | DMA block {self.block+1}/4'))
        self.time_ax.set(title=self.text('I/Q时域 · 本帧前256点','I/Q time domain | first 256 samples'),
            xlabel=self.text('本帧内时间 (us)','Time within frame (us)'),ylabel=self.text('原始ADC码值','ADC counts'))
        self.spec_ax.set(title=self.text('频谱 · Hann窗 / 1024点','Spectrum | Hann / 1024 points'),
            xlabel=self.text('基带频偏 (MHz)','Baseband offset (MHz)'),ylabel='PSD (dB re 1 count²/Hz)')
        self.water_ax.set(title=self.text('当前采集块的瀑布图','Waterfall | current DMA block only'),
            xlabel=self.text('基带频偏 (MHz)','Baseband offset (MHz)'),ylabel=self.text('块内采样时间 (us)','Sample time within DMA (us)'))
        limits=(-15.36,15.36) if self.full_band else (.3,1.7)
        self.spec_ax.set_xlim(*limits);self.water_ax.set_xlim(*limits)
        self.time_ax.grid(alpha=.25);self.spec_ax.grid(alpha=.25)
        info=[self.text(f'状态：{r.state.upper()}  帧：{r.next_frame}/{r.frame_count}',f'State: {r.state.upper()}  Frame: {r.next_frame}/{r.frame_count}'),
              'Fs: 30.72 MS/s   RX LO: 2450 MHz',
              self.text('每块65536点；块内名义时长2.133ms','65536 samples/DMA; nominal duration 2.133 ms'),
              self.text('FFT分辨率：30 kHz；跳步：1024点','FFT spacing: 30 kHz; hop: 1024 samples')]
        if frame is not None:
            t=np.arange(256)/r.sample_rate_hz*1e6
            self.time_ax.plot(t,frame.iq.real[:256],label='I',lw=.8);self.time_ax.plot(t,frame.iq.imag[:256],label='Q',lw=.8)
            self.time_ax.legend(loc='upper right',fontsize=8)
            f=frame.spectrum.frequency_hz;psd=frame.spectrum.psd;peak=int(np.argmax(psd))
            self.spec_ax.plot(f/1e6,10*np.log10(np.maximum(psd,1e-20)),lw=.9)
            self.spec_ax.axvline(f[peak]/1e6,color='tab:red',ls='--',lw=.8)
            times,frequency,history=r.history.snapshot();half=1024/r.sample_rate_hz*1e6/2
            image=self.water_ax.imshow(10*np.log10(np.maximum(history,1e-20)),origin='lower',aspect='auto',
                extent=[(frequency[0]-15000)/1e6,(frequency[-1]+15000)/1e6,times[0]*1e6-half,times[-1]*1e6+half],
                vmin=-80,vmax=10,cmap='viridis')
            self.fig.colorbar(image,cax=self.color_ax)
            self.water_ax.set_xlim(*limits)
            info += [self.text(f'频谱峰值频偏：{f[peak]/1000:+.1f} kHz',f'Peak frequency offset: {f[peak]/1000:+.1f} kHz'),
                     f'Mean I²+Q²: {frame.mean_power:.3f} counts²',
                     f'RMS/component: {np.sqrt(frame.mean_power/2):.3f} counts',
                     self.text(f'相对本块平均功率：{frame.relative_db:+.3f} dB',f'Relative to this DMA mean: {frame.relative_db:+.3f} dB'),
                     self.text(f'ROI内99%能量宽度：{frame.bandwidth.bandwidth_hz/1000:.1f} kHz',
                               f'99% ROI energy width: {frame.bandwidth.bandwidth_hz/1000:.1f} kHz')]
        else:
            for ax in (self.time_ax,self.spec_ax,self.water_ax):ax.text(.5,.5,self.text('点击“开始”回放','Click Start'),transform=ax.transAxes,ha='center')
        self.info_ax.text(0,1,'\n'.join(info),va='top',fontsize=10,linespacing=1.5)
        self.status_text.set_text(self.text('已保存的真实数据 · 无AI推理 · 功率不是dBm · ROI能量宽度不等于已验证目标带宽',
            'Saved real data | No AI inference | Power is not dBm | ROI energy width is not verified target bandwidth'))
        self.fig.canvas.draw_idle()

    def export(self,_=None):
        if self.replay.latest is None:return None
        out=self.output_root/datetime.now(timezone.utc).strftime('snapshot-%Y%m%dT%H%M%S%fZ')
        out.parent.mkdir(parents=True,exist_ok=True)
        source=dict(self.records[self.key].metadata,selected_DMA_zero_based=self.block,live_RF=False,AI_connected=False)
        save_replay_snapshot(self.replay,out,source)
        self.feedback_text.set_text(self.text('已保存：exports/'+out.name,'Saved: exports/'+out.name))
        self.fig.savefig(out/'screen.png',dpi=130);self.fig.canvas.draw_idle()
        self.last_export=out;return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--headless',action='store_true');parser.add_argument('--output',type=Path)
    parser.add_argument('--gui-smoke',action='store_true',help='Bounded Tk event-loop/export check, then close')
    args=parser.parse_args()
    if args.headless and args.gui_smoke:parser.error('headless and GUI checks are separate')
    import matplotlib
    matplotlib.use('Agg' if args.headless else 'TkAgg')
    import matplotlib.pyplot as plt
    manifest,records=load_kit(args.directory)
    if args.headless or args.gui_smoke:
        if args.output is None:parser.error('checks require a new --output directory')
        args.output.mkdir(parents=True,exist_ok=False)
    view=LearningView(records,args.directory,interactive=not args.headless)
    try:
        if args.headless:
            rows=[]
            for key,record in records.items():
                view.select_label(record.label)
                for block in range(4):
                    view.select_block(block+1);view.replay.start()
                    while view.replay.state=='running':view.replay.advance()
                    frame=view.replay.latest;frequency=frame.spectrum.frequency_hz[int(np.argmax(frame.spectrum.psd))]
                    rows.append(dict(key=key,block_zero_based=block,frames=view.replay.next_frame,state=view.replay.state,
                        last_peak_offset_hz=float(frequency),last_mean_power=frame.mean_power))
                    if block==0:
                        view.draw();view.fig.savefig(args.output/(key+'.png'),dpi=120)
            report=dict(status='passed_all_16_DMA_finite_replays_and_four_rendered_previews',rows=rows,
                        board_operations=False,AI_inference=False,interactive_physical_clicks_verified=False,
                        backend=matplotlib.get_backend(),golden_reference_module=str(Path(sys.modules[OfflineReplay.__module__].__file__).resolve()))
            (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            print(args.output);print(report['status'])
        else:
            result={'status':'interactive_not_a_check'}
            if args.gui_smoke:
                view.output_root=args.output/'exports'
                def completed():
                    try:
                        if view.replay.next_frame<2:raise RuntimeError('Tk timer did not advance multiple frames')
                        view.toggle();position=view.replay.next_frame;view.step()
                        if view.replay.next_frame!=position:raise RuntimeError('GUI pause did not freeze cursor')
                        exported=view.export()
                        if not exported or not (exported/'screen.png').is_file():raise RuntimeError('GUI export failed')
                        result.update(status='passed_Tk_event_loop_timer_pause_and_snapshot',timer_frames=position,
                            exported_snapshot=str(exported),backend=matplotlib.get_backend(),
                            board_operations=False,AI_inference=False,physical_mouse_clicks_verified=False,
                            golden_reference_module=str(Path(sys.modules[OfflineReplay.__module__].__file__).resolve()))
                    except Exception as error:result.update(status='failed_GUI_smoke',error=repr(error))
                    (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                    plt.close(view.fig)
                smoke=view.fig.canvas.new_timer(interval=2500);smoke.single_shot=True;smoke.add_callback(completed);smoke.start()
            view.toggle();plt.show()
            if args.gui_smoke:
                print(args.output);print(result['status'])
                if not result['status'].startswith('passed_'):return 1
    finally:view.timer.stop();plt.close(view.fig)
    return 0


if __name__=='__main__':raise SystemExit(main())
