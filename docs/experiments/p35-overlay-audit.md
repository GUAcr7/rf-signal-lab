# P35：合并设备树差异审查与显式加载候选

日期：2026-10-21 凌晨（北京时间）。本子任务仅阅读现有文件、解析归档源码，并生成新的电脑侧候选/证据；没有打开串口、操作板卡或界面、改写原厂资料/P30/P32/P33工程或既有实验记录。

## 验收结论

**P34 二分结果支持“两个厂家设备树分别可以使对应驱动初始化”，不足以证明整个位流正常、CDC无关或只有合并树一个缺陷。** 当前应把挂死原因维持为待定位，优先分离“FPGA加载”和“设备树应用”的步骤取得新证据。

**不应把“重新忠实拼接厂家原文”作为已确定修复。** P31 构建器本来就从两份厂家 DTBO 反编译、清理并合并；P32 最终树与厂家两树分别在电脑应用后的联合树，排除符号/句柄身份并按 provider 参数规范化引用后，恰好只有八个预期属性差异。没有发现需要靠重新抄写弥补的其他 RF 配置缺失。[八项完整差异与输入哈希](../../results/p35-explicit-overlay-20261020t160459z/factory-vs-p32-semantic-diff.json)。

## 必须修正的判断与实施路线

### P1：不能因两半分别 probe 成功而排除并行时钟、复位、CDC或数据通路问题

- 位置：`P34-bisect-bitstream-vs-overlay.md` 第67、184、186行。
- 证据：`p34-bisect1-verify` 仅读取 fabric state、DRM/fb0几何与背光目录；`p34-bisect2-rf-verify` 仅读取mode、fabric state、IIO目录与两个name。没有同次启动的 RF+显示并行证明，也没有合并 fabric 下的实际 RX DMA 传输或 TX/RX 数据一致性证据。
- 影响：若把初始化扩大为完整功能验收，会遗漏并发触发和运行时重新调频条件。
- 最小修改：结论改成“已缩小到合并加载/初始化组合，尚未定位根因”。保留58项CDC、外部IO时序与完整IQ待验收状态。
- 复测：匹配位流和DTS；一次启动里同时识别PHY/ADC/DDS和DRM/fb0；随后有限RX、帧缓冲图案、背光2与系统计时分别验收，再做并行负载。不能只数IIO目录或检测fb0。

### P1：厂家树直接拼接会撤销合并硬件需要的修正

- 位置：上述P34文档第190–200行；`START-HERE.md` 的原文拼接路线。
- 证据：P32源码第37/62行将两个DMA资源改4KiB，第41/66行改FCLK0；第272行ClockWiz AXI为FCLK1；第239行五个不同VDMA时钟名；第361行背光为通道2。实际BD导出的 `p32-pwm2-validated.tcl` 第1550/1552行对应FCLK1/200与FCLK0/100网，第1602/1604行DMA解码为4KiB，第1513行背光连 `TTC0_WAVE2_OUT`。
- 八项差异：两个DMA `reg`、两个DMA `clocks`、ClockWiz `clocks`、VDMA `clock-names`、背光 `pwms`、独立 `firmware-name`。后者是文件选择，其余均有硬件或驱动契约依据。
- 影响：还原原文会重新声明错误时钟资源并控制未连到当前背光的TTC通道0，也会重引入已知系统计时资源冲突。
- 最小修改：保留上述必要差异；通过单变量实验分离加载路径，不重做整份树。
- 复测：电脑原生FDT应用、符号/引用/地址/IRQ核对；随后在匹配合并PL的单次新启动试验，不把电脑应用当内核验收。

### P2：不能把“firmware fragment放在RF后面”直接认定为先probe后配置

- 位置：P32源码 fragment@0/1/2 后才是带 `firmware-name` 的 fragment@3。
- 本轮曾将该顺序列为候选，查供应源码后撤回直接归因：`drivers/of/overlay.c:491` 对所有fragment发出 `OF_OVERLAY_PRE_APPLY`，第511行才应用changeset并发送设备变化通知；`drivers/fpga/fpga-region.c:462–463` 在PRE_APPLY中调用配置函数，第400行执行FPGA programming。因此该份源码下，fragment序号本身不意味着RF驱动先访问未配置PL。
- 限制：运行内核带dirty标记，归档源码不是全部运行二进制的逐字复现。这是排除一个未经验证的解释，不是已经找出真正原因。
- 源码归档：本次从已校验包提取了 `fpga-region.c`、`overlay.c`、`dynamic.c`，[来源及SHA](../../results/p35-explicit-overlay-20261020t160459z/kernel-source-manifest.json)。没有改内核。

## 已制作的P35电脑候选

- [生成/检查脚本](../../experiments/p35_prepare_explicit_overlay.py)
- [显式加载用DTS](../../fpga/integration/rf-display-p35-explicit.dts)
- [原始编译、原生FDT应用与检查报告](../../results/p35-explicit-overlay-20261020t160459z/report.json)

它取自已与 `E:/p33-ttl-114312` 配对的 P33 TTL33/PWM2 DTS，删除**整个只有cells和firmware-name的fpga_full fragment@3**。保留其余fragment编号及全部设备描述。不能只删除firmware-name后留下空region fragment：供应 `fpga-region.c:373、390–397` 要求该类region overlay提供firmware或 `external-fpga-config`，否则返回EINVAL。删除该fragment使此次overlay根本不要求FPGA-region配置动作。

本次实际以原生DTC分别编译P33和P35，再以同一libfdt应用到同一归档基础DTB。逐字比较最终所有属性的hex，唯一变化是 `/fpga-full/firmware-name` 消失，**其他890个最终属性保持**，包括句柄值和引用。检查还明确保留89项AD9361初始化参数、RX/TX DMA 4KiB/FCLK0、ClockWiz输入FCLK0/AXI FCLK1、VDMA五路FCLK1、PWM2/50µs及800×480/33000kHz。

候选DTS SHA256：`c55bccff813c8464d648608f81ead597da31b3556dbc501752691d081142332d`。

候选DTBO SHA256：`fe76a72f30541e0bad273d9bb2f715718a98d4cf0e8ca375efbf4a688603a828`。

配对BD SHA256：`c373bacbfc2acc6213b60988d100f49b1a66781a009678e4a59218d99efc46f3`。这只是配对源，不代表该工程已经综合/布线/上板。后续根任务构建可能产生新的构建证据，不能用P32位流替代TTL33候选来宣称这组已验收。

## 新启动试验顺序与恢复边界

1. 保持原厂启动文件及备份哈希已核对。使用既有新启动hold机制停止S99自动加载，保留风扇；记录boot_id、mode、CPU计时源、内核taint、设备/overlay清单。已有RF或显示驱动时不得重配置PL，也不得热卸载以“清空”环境。
2. 电脑侧完成TTL33候选的真实综合/布线/时钟/DRC/CDC复核。用工具导出的裸bin，独立核对格式、来源DCP和SHA；不要用固定124字节切头规则处理任意bit文件。
3. 在没有相关驱动和overlay的新启动环境中，显式加载匹配的裸bin；串口分步保留配置前后日志、返回码与 `fpga_manager/state=operating`。若这一步失败，停止，不再应用设备树。
4. 只应用本候选一次；不重复请求firmware，也不在失败后热移除/热重试。此步成功或失败都要保存完整日志、启动ID和文件哈希，不能仅凭串口静默断言总线死锁。
5. 首先核对RF三设备名称、两个DMA驱动绑定、DRM/fb0与800×480，再验收有限RX/资源释放、实际显示图案、PWM2物理背光、时钟LOCK/像素频率和系统计时。完成单独验收后才启动并行循环。
6. 任一步未完成不改成默认开机模式。恢复采用正常重启回已校验的厂家文件；若Linux无响应，在既有U-Boot恢复路径还原**已核对长度/哈希**的厂家文件后启动。不要把硬编码0x1268当所有备份的通用大小，不通过rmdir卸载带RF/PWM驱动的overlay。

显式加载是隔离路径的实验候选，**不是已经证实的挂死根治**。若显式加载operating后应用本候选仍失败，应按受控新启动继续拆为RF-only与display-only设备片段，逐组加回并保存每次日志；不能撤销硬件匹配修正或通过更多静默重试替代诊断。
