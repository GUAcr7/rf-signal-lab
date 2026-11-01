# P06：ARM Linux 编译工具与板端验证准备（2026-10-11）

本记录区分下载/解包、交叉编译、电脑运行和真实 ARM 板端运行。仅前者通过不能宣布板卡部署完成。板卡现有固件的接收复核和JTAG身份已通过，见 [安装与板卡记录](exp-p06-install-20261010.md)。

## 工具来源和范围

复用已有 WSL2 `Ubuntu-24.04`，实际宿主为 x86_64，宿主 glibc2.39；此版本不代表板端版本。没有新装发行版、追加 Vitis、改系统 PATH 或板端 libc。已有 Windows GCC用于电脑验证，不能生成 ARM Linux 程序。

从 [Arm 官方二进制地址](https://developer.arm.com/-/media/Files/downloads/gnu-a/8.3-2019.03/binrel/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf.tar.xz)下载 `gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf.tar.xz` 到 `E:\FPGA_Tools\ARM-GNU-A-8.3-2019.03`。发生一次连接中断，首次 exit56；随后原地址断点续传完成，exit0，256,094,408 bytes。TLS验证始终启用。

[官方 checksum](https://developer.arm.com/-/media/Files/downloads/gnu-a/8.3-2019.03/binrel/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf.tar.xz.asc)是MD5：`650dc30f7e937fa12e37ea70ff6e10dd`，实际一致；它不是数字签名。另存本地 SHA256：`d4f6480ecaa99e977e3833cc8a8e1263f9eecd1ce2d022bb548a24c4f32670f5`。

归档5,911成员、未压缩1,392,151,691 bytes。解包前检查成员只位于规定根目录、无绝对或逃逸链接、无特殊设备/重复条目/特权权限、无链接父目录写入。初次在E盘经WSL解包触及180秒超时，进程停止，未执行部分编译器。保留失败证据 `results/p06-arm-cross-20261011` 和部分文件，另建 `attempt-2`，将仅解包阶段时限延长到1200秒；不覆盖失败目录。

准备入口：[p06_arm_cross_prepare.py](../../experiments/p06_arm_cross_prepare.py)。首次失败脚本和第二次实际入口分别留存在各自结果目录。

## 编译与运行验收

| 项目 | 状态 | 依据 |
|---|---|---|
| 官方下载和校验值 | 通过 | 第一次失败与断点续传记录、实际MD5/SHA256 |
| 归档成员安全检查 | 通过 | 5,911条成员清单 |
| 隔离解包、GCC目标和版本 | 通过 | 第二次解包exit0，实际GCC8.3.0、arm-linux-gnueabihf |
| Hello/FIR smoke/FIR CLI的ARM交叉编译 | 通过（编译） | 三个编译和ELF检查exit0；板端运行另行验收 |
| FIR smoke电脑运行 | 通过（Windows） | `results/p07-arm-smoke-host-20261011/report.json`，exit0，两个冲激输出及其累计值正确 |
| 18组黄金向量复用检查 | 通过（Python） | 原文件指纹和72,356个输出复核；不是ARM运行 |
| 当前板端架构、libc和/tmp挂载 | 初步通过 | 用户13:00截图：armv7l、glibc2.28、/tmp tmpfs rw且未列noexec；解释器路径及实际运行继续核验 |
| 测试包传输与板端SHA256 | 通过 | 用户下载截图的sha256sum与电脑端已验证包一致；见下载核验记录 |
| ARM程序实际运行与输出回收复核 | 通过（离线算法） | COM5实测Hello/最小FIR/18组重置重放通过，21个回收文件独立检查通过；实时接收与性能另行验收 |

实际编译使用 Cortex-A9、NEON、ARMv7、hard-float，GCC8.3.0自带sysroot。三个ELF均为ELF32/小端/ARM、EABI5 hard-float，VFP寄存器参数；解释器为 `/lib/ld-linux-armhf.so.3`，仅依赖 `libc.so.6`，所需符号版本为GLIBC_2.4。编译器sysroot不是已验证的当前板卡sysroot，不能因镜像glibc2.28而省略板端核对。

第二次流程12:34:46完成，证据见 [交叉编译报告](../../results/p06-arm-cross-20261011b/report.json)、[ELF依赖](../../results/p06-arm-cross-20261011b/elf-dependencies.json)及逐命令stdout/stderr。WSL每次启动的localhost代理提示另存stderr，下载使用Windows curl，未改WSL代理设置。

## 板端测试包和下一步

准备脚本 [p07_prepare_arm_vectors.py](../../experiments/p07_prepare_arm_vectors.py)已在交叉编译报告通过后运行。测试包包含Hello、FIR最小测试、FIR CLI、原黄金输入、预期CSV及SHA256清单。计划18组每组完成一次输入及重置重放，共144,712个复数输出，并逐字节比较I/Q、饱和标记与累加值。82个包内文件校验及ZIP CRC通过；仅运行 `sh -n` 检查Shell语法，没有执行板端脚本或ARM二进制。`ARM_FIR_ALL_PASS`是期望结束标记，当前没有这项板端实测结果。

成品：[arm-fir-check.zip](../../results/p07-arm-board-bundle-20261011/arm-fir-check.zip)，准备记录 [report.json](../../results/p07-arm-board-bundle-20261011/report.json)，独立检查 [package-validation.json](../../results/p07-arm-board-bundle-20261011/package-validation.json)。测试包入口保留为人工启动，先核对板端运行库与执行挂载；脚本拒绝覆盖已有outputs，不写持久化分区。

打包开发时先按已有API纠正case字段、四项返回值与Nx2输入格式；随后复核18组黄金数据并实际生成成品。不将这些准备修正或电脑小测试记为ARM验收。

下一步先从已有SecureCRT板端终端取得当前型号、libc与挂载状态。确认目标为ARMv7 Linux hard-float、运行库版本满足依赖、临时目录可执行后，再将测试包传到新的临时目录运行。不要写启动分区、修改libc或根据镜像假定任何目录具有持久性。

在已登录板卡且显示shell提示符的SecureCRT窗口，依次执行以下三条**只读**指令，保留全部输出；本次还没有执行它们：

```sh
uname -a
/lib/libc.so.6
cat /proc/mounts
```

第一条确认当前内核/ARM架构与主机名；第二条显示实际运行库版本；第三条确认根目录和临时目录的挂载及是否禁止执行。任何一条失败也须记录原文，不能跳过检查而替换系统库。已保存资料无法代替当前已认证终端的这些读数；此处是下一轮人工操作交接点。

此次C程序处理离线向量，不调用IIO或射频接口。即使ARM测试通过，也不等于实时采集、采样连续性、吞吐率、AI推理或FPGA上板通过。

## 13:00：当前运行环境截图核对通过；准备USB网络传输

用户已在SecureCRT执行上述指令。初次 `unname -a` 和 `cat/proc/mounts` 缺少正确拼写/空格，随后正确指令得到结果，属于输入错误，不是内核/文件系统故障。

实际为 `pzp201`、Linux `5.10.0-98231-g9dfba10b795d-dirty`、armv7l，GNU libc2.28（构建GCC8.2.0）。`/tmp`为`tmpfs rw,relatime`，未列noexec；根目录rootfs rw。截图还列`/mnt/jffs2`，但没有读写验证或采用它保存程序。截图与人工转录见 `results/p06-board-runtime-20261011/board-runtime-user-screenshot.png`、`runtime-observation.json`。

仅初步运行前提通过，GLIBC_2.4符号/解释器加载和实际ARM执行仍须由程序验收。`/tmp`为RAM临时存储，重启不应依赖它保存成果。

将已验证的包另制为83个普通相对文件的tar.gz，逐成员与源包核对内容，供板端tar使用：`arm-fir-check-20261011-1302.tar.gz`，1,414,709 bytes，SHA256 `ddda514d8077987f1b02d3267bbe6c576054ee60a19beae416a6e4181fd10ae6`。记录见 `transfer-package.json`。未解包到板卡。

实际电脑USB网卡地址为192.168.2.10/24。临时只读HTTP服务绑定此地址8765，只允许192.168.2.1读取唯一测试包，不支持上传/浏览目录，1800秒后自动关闭；未安装软件、修改防火墙或登录凭据。入口 `experiments/serve_arm_bundle.py`，启动/传输事件留存 `transfer-events.jsonl`。目前仅电脑服务就绪，板端wget、校验及执行仍为待验证；若传输失败，应先读取实际报错，不盲目改网络或安全设置。

## 13:05：板端下载与整包校验通过；等待实际ARM运行

用户最新SecureCRT截图显示wget连接192.168.2.10:8765，完整保存1381k文件到 `/tmp/arm-fir-check-20261011-1302.tar.gz`，随后实际 `sha256sum` 为 `ddda514d8077987f1b02d3267bbe6c576054ee60a19beae416a6e4181fd10ae6`，与电脑端已验证归档一致。服务历史事件记录发送1,414,709 bytes；事件中的board_checksum_verified:false仅表示服务器发送时无法核验板端，不代表随后人工校验失败，保留原始事件不改写。

证据：[下载截图](../../results/p06-board-runtime-20261011/download-user-screenshot.png)、[下载核验](../../results/p06-board-runtime-20261011/download-verification.json)。截图中的多参数command -v只显示 `/usr/bin/wget`，不据此宣布tar/cmp都已可用；sha256sum已由实际执行证实。

下一步人工在SecureCRT依次进行保护性解包、82个包内文件校验和 `sh ./run-on-board.sh`。预期Hello、最小FIR与18组重置重放比较通过，最终144,712个输出；此处未把预期结果记成实测。脚本拒绝已有outputs、不调用射频、不改固件。板端运行及输出文件回收复核仍待验证；重启前应回收结果，因为/tmp是易失存储。

## 13:17：AI经独立USB串口完成ARM执行和结果回收；离线局部验收通过

用户授权本步骤全部由AI完成。当前PNP实际识别COM5为PlutoSDR Serial Console，COM9为另一条FTDI串口。通过.NET SerialPort直接访问COM5，115200/8N1/无流控，DTR/RTS保持false，没有操作SecureCRT界面、修改驱动或争用COM9。复用项目记录中的厂商账号登录，未修改认证配置、SSH信任记录或密码。实际读取uname再次确认pzp201/armv7l。

初次登录响应把提示符附在厂商网址后，脚本过严的行首匹配造成超时；登录已成功、尚未执行测试。根据原始响应修正提示符匹配，保留失败记录 `results/p06-arm-board-run-20261011-131250`。随后tar -xzf被BusyBox拒绝（不支持-z），tar -taf也实际报invalid tar magic；检查发现gunzip可用，因此显式gunzip -c到新临时tar后再tar -xf。解压后的4,986,880 bytes tar SHA256为 `508f987544fecd948cd6a6c0d400455e5c2c7eb4fd0eceb2c02b464977bcace5`，与电脑解压值一致。不安装/替换板端tar，不覆盖原始归档，失败日志保留。

成功执行证据位于 [板端运行报告](../../results/p06-arm-board-run-20261011-131439/report.json)、同目录serial-transcript.txt：整包与解压tar校验、82文件清单检查及运行脚本均exit0。实际ARM Hello、两输出冲激最小测试、18组正式向量及每组重置重放均通过，最后 `ARM_FIR_ALL_PASS cases=18 outputs=144712`。这是板卡ARM实际执行，不是Windows或WSL代替运行。

板端wget无POST支持，base64/nc/curl均未查到可用入口；不安装额外板端软件。将outputs用板端现有tar/gzip打包，随后经COM5读取od十六进制表示并在电脑重建字节。回收压缩包1,279,088 bytes，SHA256 `56231552e9c16b13adeb163801462d10f351bd5bb0ccfbdf4c45ecdd9328d3d5` 与板端sha256sum一致。已保存 [完整结果包](../../results/p06-arm-board-readback-20261011-131559/board-results.tar.gz)、原始串口响应、回收报告与21个outputs文件。

[独立输出复核](../../results/p06-arm-board-readback-20261011-131559/output-verification.json)实际exit0：重新检查原测试包82个文件指纹，验证归档成员路径/类型/数量，18个CSV逐字节匹配原黄金参考，共144,712行，每行六整数列I/Q/两路饱和标记/两路累加值，每组前后重放完全一致；Hello、最小FIR与ARM uname文本同时复核。没有以最终PASS文字单独替代数据检查。

本次新增入口为 `experiments/p06_arm_serial_run.ps1`（Inspect/Run/Retrieve，唯一新证据目录、身份/校验/退出码检查、失败停止）及 `experiments/p06_verify_arm_readback.py`（回收数据独立校验）。失败目录与原始事件不改写；现有Git暂存区SHA256仍为 `8ead9f45d19caee3dca3792831bc4856801334a17a87c00e6080834572cbc83d`。

验收范围：ARM部署最小程序与离线定点FIR算术通过。未接实时IIO、未测吞吐/延迟、未运行AI、未烧写新FPGA或BOOT。P06整阶段与P07整阶段仍未完成。板端测试包/输出在/tmp，断电会丢失，但完整输出已回收电脑，可复核；下次先识别当前COM号/板卡身份，再使用新的临时目录部署，不能直接重复Run覆盖已有outputs。
