# 新借板 AD9361 资料只读审查（2026-10-16）

本次未连接/操作新板，未修改 D:\AD9361 资料，未运行其中任何安装、启动卡、烧录或发射命令。只读提取、渲染及审查笔记已保存在 [证据目录](../../results/p12-new-board-review-20261016)，原始提取位于 tmp/new-board-review-agent。资料里的操作步骤是参考资料，不是用户要求立即执行的授权。

## 已确认的资料范围

- 资料根目录：`D:\AD9361\AD9361`。54 个文件，总大小 3,091,408,245 字节。`source-inventory.json` 记录绝对路径、大小及手册/源码/设备树 SHA-256。
- 核心说明是创龙 2021-02-18 V1.0 的 AD9361 案例包；不是原 P201/P203 的 Zynq-7020 工程。
- `用户手册\2-AD9361案例开发手册.pdf` PDF 第 4 页：基于 ADI AD-FMCOMMS3-EBZ 射频模块与创龙 TLZ7xH-EVM 评估板，完成 QPSK 数字调制与 FM 收听。
- 同手册第 24 页及 `软件资料\Demo\hw\src\scripts\create_project.tcl`：仅列 `xc7z045ffg900-2` 与 `xc7z100ffg900-2` 两种目标。它们是资料支持的选择，尚不能证明老师借出的实物具体是哪一种。
- 第 21 页示例依赖 Vivado 2017.4 与 ADI HDL 2018_r1；当前项目原板的 2021.1 工具链不能直接视为该新板验证过的工具链。

## 接收链路与可复用内容

开发手册 PDF 第 5 页：FMCOMMS3 的 TX1A/RX1A 分别连接天线，模块接 FMC，TLZ7xH 的 J1 选择 2.5 V（FMC IO BANK 电压），评估板与 Ubuntu 主机接同一路由器。这是本案例的硬件要求，不能把 2.5 V 理解为整板供电电压。

开发手册第 6-8 页：加载匹配型号的 PL `.bin` 与设备树覆盖后出现 IIO 设备，启动 iiod，主机 IIO Oscilloscope 按板 IP 连接。第 20 页说明 PS 经 SPI/GPIO 配置 AD9361，AXI AD9361 IP 完成采样接口，AXI DMA 与 PS DDR 交换数据。因此现有本项目的 IIO 接收、保存、分析逻辑有可移植基础，仍需按新系统 ABI、通道格式、速率和接口重新核验。

第 9-12 页为 QPSK 案例：RF BW 20 MHz、Fs 61.44 MSPS、RX/TX LO 2400 MHz；DAC Buffer Output 加载 `modem_qpsk_20MHz.mat`，DAC 勾 voltage0/1；RX 勾 voltage0/1，以星座图查看。此 `.mat` 不在本目录54文件的独立文件清单中，可能由安装 IIO Oscilloscope 获得；不能声称已找到或已发送。

第 14-20 页为 FM 接收：RX1A 接 FM 天线，USB HOST 接声卡，主机显示频谱，板端 `iio_fm_radio_play` 播放。示例 Fs 22 MSPS、BW 2 MHz、LO 102.7 MHz。示例频率/IP 不是实测状态。

`软件资料\Demo\sw\src\ad-fmcomms3-ebz-overlay.dts` 实际源码：

- 第13行参考时钟 40 MHz。
- 第141行 2RX2TX，第145行 FDD。
- 第163行 A 平衡 RX 端口，第170行 TX1A/TX2A。
- 第172行 TX attenuation 10000 mdB，即 10 dB。
- 第175-183行默认 RX/TX BW 18 MHz；RX LO 2.4 GHz、TX LO 2.45 GHz；RX/TX sampling 30.72 MSPS。
- 第196-197行 RX1/2 slow-attack AGC。
- 这些默认值与手册测试时手动改的 20 MHz/61.44 MSPS/共同2.4GHz有区别；接实物必须读回，不能混用。

## 射频口与功率依据

`硬件资料\原理图与PCB资料说明.pdf` 第3页明确说明：FMCOMMS3 原理图/PCB 是 ADI 官方原文件，创龙未修改。

`硬件资料\原理图\ad-fmcomms3_reva.pdf`（4页）已整页渲染查看：

- 第2页 RX SMA：J110 RX1A、J111 RX2A，经 T105/T106 TCM1-63AX+ balun 和18pF隔直电容进入芯片差分RX A；TX SMA J112 TX1A、J113 TX2A。未见独立 RX LNA 或 TX PA，不能由此替代完整板级输入额定值。
- 第3页 FMC 接口；第4页模块使用 FMC 3P3V 与 VADJ 相关电源及板载转换。这里不能推出 TLZ7xH 整板 DC 适配器电压/电流/极性要求。

`开发参考资料\AD9361.pdf` 是 Rev.F：第1页芯片级 RX 70 MHz-6 GHz、TX 47 MHz-6 GHz、12-bit ADC/DAC，调谐信道带宽小于200kHz到56MHz；该频段是芯片能力，不是已证明该实物全部频段均达到规定性能。

同数据手册第15页 Table11：RF Inputs (Peak Power) **2.5 dBm**，且同页说明这是绝对最大应力等级，不意味着在该值或更高于操作规范的条件功能可用。**不得把2.5dBm当推荐输入电平、目标平均功率或同轴线直连许可。**

`开发参考资料\AD9361 RFPortInterface_v2.1.pdf` 第3-4页也写2.5dBm peak的条件是single-ended、ideal/lossless match、50ohm source，并强调外部匹配。该文档含2012早期描述，只作背景，不覆盖实物端口限制。

若旧 P201 当源、新FMCOMMS3当接收，仍需要旧板PA输出上限/正常电平、已知线缆和衰减器参数、新板推荐输入范围以及峰均比等依据，才能决定是否和怎样实际发射/连接。本次审查不提供猜测的衰减或功率设置。

## 屏幕的真实结论

目前**尚未证明随附射频案例能直接驱动老师实物上的屏幕**。

- 两份案例手册显示部分是 Ubuntu 主机上的 IIO Oscilloscope，不是板载屏直接运行；`1-AD9361案例环境搭建.pdf` 第33页解释软件获取时域/频域/星座/互相关，第46-47页是在Host安装。
- 实际 `system_bd.tcl`、顶层Verilog与 `system_bd.pdf` 第1页只发现射频接口、FIFO、DMA、PS等；未见LCD/HDMI/VDMA/VTC等显示IP或顶层端口。
- 只读解析镜像 `软件资料\Linux\Kernel\image\linux-xlnx-ad-fmcomms3-ebz\tlz7xh-evm.dtb`：model=TLZ7xH-EVM，2个Cortex-A9 CPU，serial stdout=115200n8；未见display/panel/framebuffer/hdmi/lcd节点。`tlz7xh-evm-dtb-tree.txt`可复核。
- 但是 `软件资料\Linux\Filesystem\rootfs-ad-fmcomms3-ebz.tar.gz` 中存在 Qt5.7.1、Xorg、tslib配置和 Qt linuxfb/xcb/eglfs 平台插件，是可复用图形软件基础。不能把有库或配置说成显示硬件已接通。
- 需要老师提供 TLZ7xH-EVM 基础板用户手册/原理图、实物型号和屏型号/接口、现用 SD 系统备份及其屏幕演示工程；或实物接入后只读查 `/proc/fb`、`/sys/class/drm`、设备树、Qt版本及当前程序。为保留老师可工作的屏幕系统，不宜盲目照本包重新制卡/加载射频-only PL。

## 软件兼容性只读证据

### 产品目录补查：已提供的显示接口与供电标签

进一步将扫描型《Tronlong产品汇总手册(2020.8).pdf》37页全部渲染浏览，PDF第20页（印刷19页）明确TLZ7xH-EVM带HDMI IN/OUT、LVDS、Backlight、LCD RES，电源标注12V DC@3A。该页属于XC7Z035/045/100系列；本射频案例仍只提供045/100工程。不能把目录系列最大资源或频率套到每个型号。

因此“完全没有显示接口/整板电源信息”的初步判断应修正：**已有平台接口名和供电标签，仍缺实物型号对应、插头极性/尺寸、屏型号/时序/pinout、驱动及射频显示共存工程**。目录信息不授权改变未核实实物的供电。

PDF第21页的TLZ7x-EasyEVM是另一种Z7010/7020平台，第35页的多款显示模块也没有证明老师实物属于哪款。完整图与修正依据保存在 [目录补查证据](../../results/p12-new-board-catalog-20261016/catalog-addendum.md)。射频-only PL/DTB未见显示链路的观察仍成立；优先保留老师现用显示系统。

对 rootfs 压缩包只读扫描28828个成员，保存 `rootfs-inventory.json` 与部分小配置文件；未解包/执行整套镜像：

- `etc/issue` = `PetaLinux 2017.4`。
- `etc/version` = `20200630054918`（构建标签，不是实物当前版本）。
- `lib/libc-2.23.so`：ELF32、ARM、小端；glibc2.23。
- `usr/lib/libiio.so.0.20`，`usr/sbin/iiod`，`usr/bin/iio_info`，`iio_fm_radio`、`iio_fm_radio_play`。
- `usr/lib/libQt5Core.so.5.7.1`；平台插件 `usr/lib/qt5/plugins/platforms/libqlinuxfb.so`、`libqxcb.so`、`libqeglfs.so`。
- rootfs inventory未发现 `osc` 或 `iio-oscilloscope` 实机可执行名（只匹配上述成员清单时无命中）；不宣称该应用已预装。
- `uImage`64字节头Name字段为 `Linux-4.9.0-rt1-xilinx-g0e07141-`。

原 P201 的当前实测 glibc2.28/libiio0.24 与这个资料镜像不同，原ARM程序不能不检查ABI就当即用。图形程序也应使用新板实际系统的 Qt/sysroot。资料镜像不等同于老师已安装系统。

## 已读但未执行的高影响步骤

开发手册第4-6页包含重新制 Linux 启动卡、U-Boot saveenv、加载PL与设备树；第5页有天线TX测试。这些均未执行。若重用其指导，应先备份老师的现有系统、核实实物型号、屏幕与射频组合工程，避免覆盖已工作的显示或发射配置。

## 后续验收分层

1. 新板实物型号、供电与现用屏显示基线确认，保留镜像。
2. 只读确认IIO PHY/ADC、RX端口、扫描格式、Fs/LO/BW/AGC。
3. 无受控源时先验证真实RX数据保存/重启，不声称目标识别准确。
4. 按实际板级电平完成衰减链路预算后，以受控单音验证频率，再用BPSK/QPSK/16QAM已知波形验证带宽/识别。
5. 将已有 ARM 分析/模型按实际 ABI 和采样条件移植到新板；屏幕与射频必须共存，最后脱离电脑验收。
