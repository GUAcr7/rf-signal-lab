# P65：COM10固定入口、文件恢复和正常结束状态修复

日期：2026-10-25，北京时间。用户明确选择已工作的COM10，要求继续项目。本阶段完成电脑控制入口适配和实板启停/源文件恢复；不宣称完成触屏控制、排针回环或新射频验收。

## 本阶段交付

- `configs/board-connections.json`保存用户选择`usb-console`。按VID0456/PIDB673、Pluto串口描述和唯一候选选择端口，再核验Linux pzp201与`PUZHI PZSDR P201`型号；不写死COM10编号。
- 固定入口支持`--tx-transport usb-console|ftdi`单次覆盖。默认读取配置，不在端口缺失时静默换设备；原FTDI模式保留。生产入口和demo的子步骤使用同一连接选择。
- 通过已拥有的Linux USB终端恢复RAM源包，采用有界uudecode传输，核验压缩包、展开tar和每个文件SHA，继续沿用原guard检查。无需为这一步修改Windows网卡地址或依赖192.168.2.10文件服务。
- 修正自然到时结束被误判未知的情况：仅在`finished/duration_complete`、exit0、无所属接收进程、DMA/四路扫描全0、同boot的AI STOPPED且类别-1，并有完整原生清理证明时判定干净停止；不改原始进度文件。

## 原始证据

| 检查 | 结果 | 报告 |
|---|---|---|
| 改动前快照 | 入口、规则、测试、恢复文档保留 | [快照](../../results/p65-before-20261025t111057z/report.json) |
| 首次新入口读取 | 旧板成功，新板Windows串口错误31，完整保留失败 | [首次状态](../../results/p59-status-20261025t111227214214z/report.json) |
| 用户重插新板串口后 | 两板身份/内核/配置可读，发现新板正常结束状态被误判 | [状态证据](../../results/p59-status-20261025t111427733546z/report.json) |
| 正常结束规则修复 | 原生summary五项清理证明齐全，判定STOPPED | [修复后状态](../../results/p59-status-20261025t111935156963z/report.json) |
| 旧板数字零源 | 在idle/scale全0条件下将raw归0并核验；不是绝对RF静默证明 | [零源](../../results/p59-source-off-20261025t112123099177z/report.json) |
| 冻结源包恢复 | COM10传940865字节，远端SHA及每个成员通过，guard只检查不发射 | [恢复](../../results/p59-prepare-source-20261025t112330725700z/report.json) |
| 新接收会话启动 | 保留旧RAM目录，使用原P56程序，进度更新，AI要求本次校准 | [启动](../../results/p59-start-20261025t120321232755z/report.json) |
| 正常停止 | 清理验证通过，AI STOPPED，串口关闭 | [停止](../../results/p59-stop-20261025t120418974164z/report.json) |
| 停止会话归档 | 5个文件逐块及整体SHA核验，历史113条；不计算新AI准确率 | [归档](../../results/p59-p65-archive-stopped-20261025t122532907857z/report.json) |
| 离线控制/传输检查 | 最终58项通过，包含误认设备、歧义端口、缺失清理证据及传输失败 | [JUnit](../../results/p65-control-tests-20261025.xml) |

本阶段没有RF发射、PHY参数更改、PL加载、板卡重启或新模型训练。数据恢复仅写旧板tmpfs；接收启动仅新建应用会话，非冷启动。原模型、特征处理、RX原生二进制与持久启动选择保持原验收版本。

## 实际发现和修复的问题

1. 原入口硬性要求FTDI，用户已工作的COM10无法进入：增加显式连接配置及型号核验，不把任意串口号当身份。
2. 新板当前会话正常运行900秒后记录`state=finished, reason=duration_complete`，旧分类器只接受`stopped`：新增受原生清理证明约束的正常完成分支。原记录未重写为stopped，也未把单次状态读取当成新的15分钟验收。
3. 原源包恢复要求电脑USB网卡固定地址，COM10本身已可通信但传文件仍受网卡约束：USB终端模式直接有界传输并校验；原FTDI/HTTP路径保留。

## 编辑器准备与当前边界

官方USART HMI安装包此前下载在E盘。现通过只读MSI表和Windows CAB解压，将141个程序文件还原到E盘，未执行MSI安装、自定义动作或安装驱动；[解包记录](../../results/p65-editor-unpack-20261025t112418z/report.json)。入口为`E:/FPGA_Tools/TJC-USARTHMI-20261025T112418Z/app/APPDIR/USART HMI.exe`。

程序目标运行时为CLR2（文件含v2.0.50727），本机初次启动返回0x80131700。尝试仅在程序目录添加微软文档支持的CLR4启动配置后出现ApplicationRUN.resources/achmiface.resources资源加载提示；此兼容尝试未验收，程序已关闭，配置改名为`.p65-trial-disabled`留存，未修改厂商EXE/DLL。

已要求用户启用匹配的.NET Framework3.5，用户第一次反馈下载/安装出错，随后要求“重新下载”。本轮已通过Windows自带Fondue重新发起，实际窗口进入“正在下载所需的文件”。只有系统明确完成且编辑器实际启动后才能记录环境成功；不得以进度条接近满格宣称安装完成。

后续系统日志显示该次下载100%后在20:14:31以`0x800f0820 CBS_E_CANCEL`结束。未点击取消按钮，取消来源未确定。20:17再次以管理员DISM `/Enable-Feature /FeatureName:NetFx3 /All /NoRestart`重试，记录在[系统重试](../../results/p65-netfx3-system-retry-20261025t121739z/report.json)。截止保存时仍在等待Windows更新依赖，尚不算安装成功。不要把DISM初始化日志中的`unknown option featurename`内部路由记录单独当成最终命令失败，实际已进入CBS启用流程。

从Windows Delivery Optimization缓存读取完整71321276字节的NetFx3包，按系统ActionList中的SHA256 `dc3af93af5c64dc115409437d31018baf2c3c46167806a599124bc905ae512f6`匹配并复制到E盘；读共享流避开缓存写入占用，未改变缓存文件、ACL、服务或策略。直接复用已过期的HTTP下载地址返回403，HTTPS替换域名出现证书名称不匹配，未绕过证书校验。正式恢复用已校验的E盘包，不使用这些失败响应作为安装包。详情见[恢复清单](../handoff/resume-p65-20261025.md)。

该运行环境步骤不等于HMI/TFT工程交付；当前仍仅有P63页面设计，尚未编译/下载屏幕。原实物型号与官方参考后缀/接口对应、J19物理引脚和电平核对仍待完成。

### 最终处理结果（20:54—20:56）

在线DISM在34%停滞超过半小时，用户要求不行就重新开始。核实PID14392、创建时间和完整命令归属；辅助进程附着后只允许控制台成员为这两个进程，发送正常Ctrl+C取消请求。DISM退出0x800704c7并关闭CBS会话，明确无需重启；无强制终止系统服务。确认不存在其他DISM后，以已校验E盘源运行`/LimitAccess /NoRestart`，约96秒返回exit0、NetFx3 Enabled、CLR2 DLL存在。[安装与取消证据](../../results/p65-netfx3-offline-20261025t125224z/report.json)。

从APPDIR启动厂商EXE，已实际观察主编辑窗口，UI显示版本1.68.2、进程响应正常，无此前资源加载错误；[界面截图与原始可访问性记录](../../results/p65-editor-verify-20261025t125645z/report.json)。编辑器保持打开。此前“安装未完成”描述均为历史步骤，现已解决。没有重启电脑、没有创建HMI/TFT、未操作板卡。

微软依据：[supportedRuntime配置](https://learn.microsoft.com/en-us/dotnet/framework/configure-apps/file-schema/startup/supportedruntime-element)、[Fondue系统组件命令](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fondue)。

## 与P64的关系

P64焊接前的UART0内部512字节回环仍只是历史板内试验，通过临时设备树/候选PL启动，没有永久选择。重新上电回原文件后不能假设/dev/ttyPS1仍存在。P64中新增SD试验文件的旧staging报告继承了`persistent_file_writes=false`默认值，但实际确有新增`p64-uart.bit/dtb`，以其added_SD_files、串口原始命令和备份为准；P65明确纠正此元数据含义，未篡改该旧报告。

当前使用COM10继续Linux软件工作，不再要求用户修复COM9或安装排针作为前置。若后续需进入U-Boot/硬件JTAG，应另行验证通道；不能把COM10的Linux终端当成上电前JTAG调试器。

恢复顺序：先固定入口status，核实本次boot和接收状态；源包与校准都按当前会话重新确认。任何RF发送仍需实际受控接线核对及显式`--rf-link-reviewed`，不根据“USB已连接”自动批准RF。
