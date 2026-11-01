# HW-036：在合并RF/LCD配置上复测已知射频源

日期：2026-10-22（北京时间）。本轮阶段已完成：完整数据回传、逐窗口质量判定、已知单音写屏独立复核及自启动恢复通过。父检查点P45已通过一次受控真断电后的自动接收/频谱显示及超过600秒实体动态确认；本阶段不重复更换FPGA或重启。

## 条件与采集

用户直接确认旧P201 TX1至新板RX1A保持之前的射频同轴连接，`results/p46-human-RF-link-20261022.json`。两板只读核对`results/p46-preflight-20261022T112328Z/report.json`：旧板boot `79ec21ce-b1d7-4069-83d7-50f540732849`，新板boot `343afe82-88e6-4a03-a5d4-c09ee6929e36`，kernel taint0、DMA均idle。旧板RAM已在重启时丢失，发射配置仍为Fs30.72MS/s、LO2450MHz、BW18MHz、TX gain −10dB/端口A；新板RX1 manual0dB/A_BALANCED。没有提高功率或写RF属性。

旧板恢复包重用已验证的发射ELF SHA `0a188e1e1c0c19a165231c1d5589ff5d72adbf284d98d2bdf39cfc6a65b1163b`及冻结源码。三种调制的256峰值源逐字节重现历史文件；单音先重现历史512峰值字节，再只降低为256。最终压缩包/解压tar/全部成员SHA及四支native --check通过，守卫inspect确认RF/DMA rate、端口、TX gain和DDS scale0。有效恢复`results/p46-ready-20261022T113936Z/report.json`。

新板沿用P36已测试ARM完整返回缓冲录制器，不用P27稀疏诊断，也不把P42的8192点前缀当65536点。未发射的1缓冲smoke通过，`results/p36-full-rx-board-20261022T112930Z/report.json`。为使用严格通用归档门禁，仅暂时把下一次S99board选择恢复原guard，记录`results/p46-startup-pause-20261022T112910Z/report.json`；未执行original start，没有卸载任何驱动或重配PL，归档后须重新启用原持久wrapper。

真实试验`results/p46-known-20261022T114115Z/report.json`已完成单音、BPSK、QPSK、16QAM四次发射。每次原生守卫30秒上限，数字单分量峰值256，数字偏移+960kHz。每种信号保留4个完整RX1 I/Q返回缓冲，每缓冲65536帧/262144字节，共每种1MiB。四次均确认TX退出0、buffer释放、DDS zero source readback、RX buffer/scan0、RF属性不变。RF物理静默及绝对功率未用仪器复测，不能凭清理日志宣称无LO泄漏。

## 本轮修掉的工具问题与保留原证据

- 首次IIO枚举使用两行相邻正则，旧板回显把下一条token插进path/name之间，导致误报设备不齐；`p46-preflight-20261022T112216Z`保留。改为单行带边界的path/name帧，缺失/重复拒绝；新预检通过。
- `p35_uart_files.upload`误用于没有base64 applet的旧板，原工具只检查“准备好”标记，未检查decoder存在，向已经退出的shell发送了编码行；最后EOF退出登录。原失败`p46-source-20261022T112638Z`保留，没有提取或运行TX。已增加command-v与decoder退出检查，缺少工具时在任何文件/终端/载荷操作前拒绝；回归通过。旧板改用已支持的uudecode封装，逐包SHA核验。
- Echo关闭后，shell提示符与返回token/sha行共行，导致旧串口封装未识别完成；`p46-restored-20261022T113210Z`及未发射试验`p46-known-20261022T114011Z`保留。P46封装的token明确前导换行；真实采集会话暂存/恢复PS1并关闭/恢复echo，不修改全局终端默认值。
- 旧板tar未编译-z支持；上传包已经SHA正确，但`tar -xzf`拒绝，`p46-restored-20261022T113416Z`保留。使用独立gzip解压并核验未压缩tar SHA，再tar -xf，无需再次传输。
- 测试夹具把整块524288字节数据作为参数ID，导致Windows测试路径过长、原XML出现setup/teardown错误；原`p46-host-gates-20261022.xml`保留。改用短参数名称，修正后8项通过`p46-host-gates-fixed-20261022.xml`，不是硬件故障或算法失败。

## 数据解释与验收门槛

`results/p46-quality-plan-20261022.json`在分析新RF数据前固定了本轮筛查门槛：已知源相关度至少0.99、已知符号EVM不高于−25dB、后半段符号错误0、观察到的ADC端点比例0。它们是本轮诊断门槛，不冒充最终任务书/无线标准指标。每个DMA独立估载波/源位置并滤波；失败窗口保留，不跨未知缺口拼接。若比较源位置，只能给131072点周期的模进度，不能排除整周期丢失。

已知调制、实际发送符号均显式提供，这不是盲AI分类，也不是独立BER测试。四个窗口共享循环随机源，不能当成独立训练/测试集。功率是ADC数字counts²，不能当dBm；频偏为两台未校准RF时钟相对结果，不能归因单独板卡或当绝对频率指标。当前仍保留lossless_proven=false。

## 恢复工具补强（不重复发射）

移除了`p46_prepare_sources.py`中的自动板端上传和tar -z路径，现在只在电脑生成已冻结包；`results/p46-source-20261022T121954Z/report.json`已成功执行且没有打开串口。`p46_restore_tx.py`改为必须显式提供源包报告及新预检报告，读取本次boot，不再硬编码上次启动；上传前在电脑校验守卫固定SHA、四源峰值/字节布局、gzip大小、tar成员白名单/类型/内容。板端使用uudecode及分开的gzip、tar，解压tar和全部成员再次SHA校验。5项正反例通过，`results/p46-restore-package-tests-20261022.xml`，覆盖被改文件、超峰值、tar额外路径及内容不一致。该通用恢复版本没有额外做一次实板上传，不能把主机测试算成新板端验收；原成功实板恢复和试验执行版本均完整留存。

## 完成结果与证据（覆盖前文临时状态）

完整归档 `results/p46-archives-20261022T114430Z/report.json`：四种源共16个完整返回缓冲、4MiB原始I/Q均到电脑，压缩/解压SHA与板端记录一致；不是只挑最优窗口。未发射smoke原始262144字节也已回传，`results/p36-file-archive-20261022T115205Z/report.json`。

质量判定 `results/p46-analysis-20261022T115205Z/report.json`，图见其quality.png：全部16窗口通过。三种调制相关度最小值分别0.998389、0.998500、0.997731，ADC端点比例均0；每组四窗口EVM范围不到1dB。

| 调制 | 已知参考EVM（dB） | 后半段检查符号数 | 错误数 |
|---|---:|---:|---:|
| bpsk | -37.96 至 -37.43 | 1004 | 0 |
| qpsk | -38.55 至 -38.04 | 1004 | 0 |
| qam16 | -37.60 至 -36.75 | 1004 | 0 |

载波/源对齐使用整个窗口；上述3012个已知符号的0错误不是独立BER。各调制源位置模进度均为+1采样，不能排除整个周期丢失。四组总原始帧名义时长34.13ms，分属不同发射会话，不能拼成连续ADC时间或证明长稳。

单音相对名义+960kHz约多33.84kHz，为两台未校准RF参考的相对结果；不能归因单独板卡或宣称绝对频率达标。先前20至32dB块间质量跳变在本轮冻结条件下没有重现，**历史故障根因仍未关闭**，不能写成已根治。

补充已知单音→P42接收/分析/显存写屏：`results/p46-panel-20261022T120816Z/report.json`，8.003秒更新16次，使用完全相同已验收ELF。第33频点对应+990kHz，独立NumPy与板端FFT、RMS、总功率一致；原始最后显示前缀32768字节及1536000字节显存均归档，`results/p42-review-20261022T120918Z/report.json`。屏幕回读PNG是显存图，不是实体屏照片或本次动画人工确认；P45的实体动态确认仍仅属于P45。显示保留no AI，不把参考解调当盲识别。RX在TX提交后8.875秒确认结束，位于30秒限时发射之内，原生TX清理及8路DDS raw0确认。

短时单音试验的同boot时钟门禁增加6项通过，`results/p46-panel-gates-20261022.xml`。该门禁分别核验受控冷启动来源、trial/readback SHA、实际boot及驱动/寄存器率一致性；没有把冷启动伪装成主机软件重启。P42原native源码、ELF和公共审查算法未修改。

归档结束已重新选用持久P43 wrapper，`results/p43-enabled-20261022T121047Z/report.json`；只读终态`results/p43-status-20261022T121209Z/report.json`确认boot一致、taint0、RX buffer/scan0、无活动接收、无pending/disabled、串口已关闭。当前板仍通电，未关机。保存包`results/p46-checkpoint-20261022T122202235876Z/report.json`覆盖代码/记录/状态及引用的原始数据，逐项SHA和ZIP CRC检查。

下一步依赖：先做独立会话/不同随机种子的已知源重复采集并排除数据泄漏，再做真实信号盲分类及板端接入；更多冷启动/长稳、0xFF根因与真实故障回退另行验证。CDC/外部时序、物理PCLK/绝对RF功率、无损连续性仍保持开放。
