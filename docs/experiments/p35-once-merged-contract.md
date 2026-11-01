# P35：一次新启动的合并工程试验契约

日期：2026-10-21。脚本：[p35_once_merged_trial.py](../../experiments/p35_once_merged_trial.py)。启动保持模板：[p35-once-hold.sh.in](../../board/boot/p35-once-hold.sh.in)。**本子任务只编写和离线静态检查，没有打开串口或执行试验。** 由主任务独立审阅、确认构建/当前状态后再执行。

## 输入门槛

仅接受三个必填参数：`--expected-boot`、`--bitstream-report`、`--overlay-report`。

- 原生位流报告必须为 `schema=rfsig.p35_ttl_bitstream.v1`、`status=passed_TTL33_native_bin_not_deployed`，并含位流路径、完整SHA/长度、`candidate_BD`及SHA、`native_bin_verified=true`、`TTL33_clock_verified=true`、`no_auxiliary_LVDS_PLL=true`和完整原厂固件哈希字典。原生 bin 还检查已验证的 loader 前缀与8MiB UART上传上限，不截 `.bit` 头。
- 显式加载 overlay 报告必须为 `rfsig.p35_explicit_overlay.v1`、`passed_PC_only_explicit_load_overlay_not_deployed`，全部结构检查通过；dtbo、源、配对报告与当前BD的SHA均匹配。与位流必须是同一BD。实际DTBO再次解析，任何 `firmware-name` 属性都拒绝，避免 overlay 隐式第二次配置PL。
- 两份输入报告的字节SHA随本次记录保存；长时间上传/重启后重新检查，不能悄然改用另一份有效报告。

## 运行边界

1. 只由本进程持有 COM8。确认板名、指定 boot_id、tainted=0、RF模式、无实验应用和活动RX缓冲/扫描；确认仓库中的已验证 S99guard 与板上相同。原厂 `ad9361.bin`、`display.bin`、`system_wrapper.bin`、两份DTBO按本轮已恢复哈希逐一检查。
2. 使用已验证的 P35 UART 上传工具，先传到唯一 `/tmp/p35-*` 路径并核SHA；再复制到从未存在过的独立 `/lib/firmware/p35-ttl-<UTC>.bin`、`p35-merged-<UTC>.dtbo`。**不覆写任何厂家固件、overlay、BOOT、基树或模式文件。** 候选文件要持久化后才重启，不能依赖 `/tmp` 跨启动。
3. 备份、核SHA并以同目录 rename 安装一次保持脚本。该脚本拒绝在安装它的旧boot执行；下一次新boot保留风扇，首先把持久备份的原guard恢复并sync、核SHA，写 `/run/p35-hold-boot` 后返回init，**不加载任何PL/overlay**。
4. 只发起一次正常重启，保存完整UART原始接收字节。每次read最多45秒；最多两个45秒窗口等登录。新boot必须不同，hold标记必须等于新boot，原guard必须已恢复；确认configfs已挂载、overlay为空、没有RF三件套或DRM/fb0，才进入试验。
5. 再核候选文件与输入报告SHA；显式写独立原生bin文件名到fpga_manager一次，要求operating；随后应用**无firmware属性**的设备overlay一次。没有自动重试、热移除或热回滚。
6. 成功检查为同一新boot上的PHY/ADC/DDS名字、DRM与fb0 800×480、tainted=0、软件时钟回读FCLK0约100MHz/FCLK1约200MHz/clk_out1约33MHz（允许1000Hz的整数报告差）、clocksource、完整kernel日志和原厂文件仍未改动。状态只称“驱动probe与软件时钟回读通过”，不称RF数据/物理像素或LOCK/并发吞吐通过。

## 超时与恢复

任何失败都保存准确阶段，停止发送后续检查命令；只被动收尾UART最多12秒然后关闭串口，不把沉默包装成通过。记录guard是否已独立证实恢复、一次hold是否可能仍待执行，不自动再次配置或重启。

若已证实hold内恢复guard，则以后**普通重启**会按未更改的RF模式与原厂固件走原guard。成功后默认保留本次合并工程运行，便于主任务接着做独立的有限RX/绘图测试；不是永久安装。普通RF重启时guard会按其既定staging逻辑把原厂RF文件复制为 `system_wrapper.bin`，这是原guard行为，不应误认候选改写默认文件。

UART RX保留原始字节；TX也记录，但登录密码（如果出现）写作脱敏标记，不把已有板卡凭据复制到实验记录。读取/上传过程发生的字节均经过同一记录包装，包括上传工具的drain。

原厂内核热卸载缺陷、冷启动0xFF、未关闭的CDC、外部IO时序和物理LOCK验证仍各自保留。这个试验只隔离“显式先配置、随后一次probe”流程，不能宣称已经证明P34挂死的唯一根因。
