# HW-031：一次性板端自主启动与两分钟接收/显示

日期：2026-10-21晚（北京时间）；沿用P39最终原生C程序和P37安全M16.5/D2/O25合并硬件。上轮重启/断电观察见[HW-030](exp-hw-030-boot-recovery-and-cold-observation.md)。

## 验收结论与限制

**这一次新启动中，板端启动脚本自行完成合并PL/overlay初始化、RX配置及有界频谱显示；主机没有在登录后发送装PL、应用overlay或启动monitor的命令。** 两分钟完成235次分析/CPU写屏，正常停止；同boot独立确认RF参数、buffer/scan释放、taint0、guard恢复，时钟后验及归档IQ的NumPy复核通过。

这是一次性、120秒有界启动试验，不是“每次通电永久自动运行”或无限运行版本。临时S99 wrapper在新boot加载PL前就恢复原始S99board；下次普通重启仍按厂家RF-only启动。未更换默认固件、BOOT、base DTB或board-mode，没有启动TX。用户本次只答“只看到 RX STOPPED，没观察到更新”，所以**本次实体动态人工确认仍为false**；P39早先的实体运动确认只作为历史证据。不能混同机器写屏计数和物理LCD FPS。

## 一次性启动实现

- `board/boot/p41-monitor-once.sh.in`：必须是与armed boot不同的新boot，且原guard SHA和p35-hold标记匹配；程序/位流/配对DTBO哈希通过；无RF、显示及overlay绑定才单次装PL+单次应用overlay。按唯一PHY/ADC/DDS名字确认、先idle再设manual0dB/2450MHz，Fs30.72MS/s/BW18MHz不变；只解绑framebuffer vtcon，保留UART console。无热卸载、无热重试。
- `p41_boot_templates.py`：严格路径/UUID/SHA/时长输入；复用已审查hold模板，将原guard恢复并sync后才调用独立runtime。runtime前40秒启动期限，monitor另有135秒timeout和22秒终止后备；应用自身120秒停止/join/释放。后备期限不是已验证的故障自恢复机制。
- `p41_autonomous_once.py`：先验证本机已归档的P40 suite、源码/ARM构建、实际shell测试和配对产物，再上传到新独立RAM/`/etc/p41-20261021T153301Z`。验证当前目标BusyBox timeout在init脚本正常返回后保留后台子进程的行为；保存原guard备份后才原子arm、sync并发出一次普通reboot。全程单串口owner，无并发板端操作。
- 新启动自动日志依次为ORIGINAL_GUARD_VERIFIED、EMPTY_BINDINGS_VERIFIED、PL_ATTEMPT=1、OVERLAY_ATTEMPT=1、MONITOR_LAUNCH、BOUNDED_MONITOR_LAUNCHED。/proc/uptime在发起launch前为7.76秒，它不是第一张物理画面出现时刻，也不是端到端RF延迟。原始启动UART证明上述marker早于login。

## 原始证据

- 本轮试验：`results/p41-autonomous-once-20261021T153301Z/report.json`，boot=e879f99c-bffa-4fa6-b3fd-af56ab9e996e；同目录有实际执行源、runtime.sh、boot.sh、monitor二进制、完整启动UART、autonomous-boot-log.txt及program.txt。
- 本轮post-accept：`results/p41-review-20261021T153805Z/report.json`，6阶段逐项退出码/报告SHA。
- 本boot时钟后验：`results/p37-clock-accept-20261021T153822Z/report.json`。独立live DT地址/driver gate后读LOCK和DRP，软件/寄存器M16.5/D2/O25一致；未仪器测外部PCLK。自动runtime在启动时只作软件33MHz率门槛，独立LOCK核验是本次应用结束后的主机后验，不冒充启动前仪器测量。
- 原始最后显示前缀和framebuffer均已回传电脑，分块SHA/gzip CRC/总SHA核验通过；`results/p39-offline-review-20261021T153853020136Z/report.json`独立NumPy核对峰值、bin、RMS和频谱总功率通过。回读图`results/p39-offline-review-20261021T153853020136Z/screen.png`已查看，上下均RX STOPPED，不是实物照片。
- 用户回答单独记录`results/p41-checkpoint-20261021T154630949661Z/human-observation.json`，不改写机器试验原记录。

## 机器摘要

```json
{
  "schema": "rfsig.latest_panel.v1",
  "status": "pass",
  "reason": "duration_complete",
  "duration_ms_requested": 120000,
  "UI_interval_ms_requested": 500,
  "elapsed_software_s": 120.005748,
  "published_prefixes": 56248,
  "consumed_prefixes": 235,
  "last_display_sequence": 56056,
  "UI_overwritten_prefixes": 56012,
  "pending_prefixes_at_stop": 1,
  "display_updates": 235,
  "retained_prefix_bytes": 32768,
  "prefix_frames": 8192,
  "frames_per_refill": 65536,
  "source_format": "le:S12/16>>0",
  "worker_started": true,
  "worker_joined": true,
  "refill_error": 0,
  "buffer_created": true,
  "buffer_released": true,
  "context_released": true,
  "cleanup_unconfirmed": false,
  "RF_before_valid": true,
  "RF_after_matches": true,
  "RF_attributes_written": false,
  "TX_API_loaded": false,
  "lossless_proven": false,
  "ADC_gaps": "unknown",
  "analyse_only": false,
  "maxrss_kib": 2640
}
```

发布=消费+UI覆盖+末尾待消费。每refill65536帧，只复制前8192帧到最新信箱，UI未消费的旧前缀可被覆盖；本次仅保留最后实际显示的32768原始字节。UI覆盖不是ADC丢样计数；未保留全流，无独立ADC序号/overrun证据，ADC gaps unknown、lossless=false。输入未知，近DC峰不能说成检测到已知RF目标，功率不是校准dBm，没有AI分类。

## 测试与实际纠错

- `results/p41-preparation-20261021T152204Z/report.json`：8项实际POSIX shell在隔离临时目录执行，覆盖恢复顺序/后台子进程存活、旧boot/错误guard/runtime/bin SHA、已有overlay/RF、失败probe没有二次PL/overlay。源哈希前后固定、原始模板sh -n通过；不是硬件驱动仿真或目标启动验收。
- `results/p41-common-evidence-gates-20261021.xml`：15 passed，扩展严格的P41已结束/idle/同boot/guard恢复/新启动证据门槛，保留原P38/P39规则。时钟后验允许已验收的P41启动报告，所有寄存器/软件率校验不变。
- 第一次shell测试6 failed/2 passed，来自测试目录映射把/proc/sys二次替换，以及Windows不能直接创建含冒号的iio:device目录。失败XML和测试源码保留（results/p41-shell-tests-20261021.xml、p41-shell-attempt1-source.py）；修正仅影响测试副本的单遍绝对路径映射/目录名，实际部署shell不用测试根目录或假硬件。后来8项通过，未删负例或改为无条件成功。
- 目标板独立验证timeout后台存活原语通过，随后真实启动及两分钟应用完成；没有把WSL的timeout行为直接当成BusyBox目标证据。

## 当前状态与后续任务

原guard已恢复、默认mode仍rf、RX idle、串口关闭，无后台monitor/TX，未再次关机。`/etc/p41-20261021T153301Z`保留为休眠的试验副本，不等于永久启用自启动。当前权威状态p41_current，恢复步骤见[RESUME-P41](../handoff/resume-p41-20261021.md)。

接下来先实现有受控停止和有界日志的长时间运行，做更长稳定性/取消恢复，再将已验证路径做成可回退的持久启动并另做真断电试验。厂家0xFF根因、58项CDC、7输入/29输出外部延迟缺项、物理PCLK、ADC连续性、已知信号质量和真实AI仍开放。本次P41是软件重启，不能继承P40厂家RF冷启动成功而称“P41冷启动已通过”。
