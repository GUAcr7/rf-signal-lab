# P63 旧P201触屏控制组件

这里只包含无IO的控制状态机、TJC回包解析与检查工具。不是已部署的屏控发射服务，没有UART设备打开、IIO操作或发射进程启动功能。主线P59双板控制和冻结AI均未改动。

## 成品与接口

- `panel_logic.h`：8个状态，四类信号预设，8～60秒时长，应用检查、启动回执、停止和清理确认。
- `panel_wire.h`：逐字节解析标准触摸/页面/数值/字符串及状态回包，最大字符串128字节，错误清缓冲并返回-1。
- 两个`*_check.c`：只接受自检或stdin回放模式，拒绝硬件参数。
- 页面与计划控件ID见`configs/tjc-source-page.json`；PNG为设计预览，不是HMI/TFT文件。

按钮仅路由page0、release0；1～4信号，5应用、6开始、7停止、8/9时长减/加。IDs尚未经编辑器编译确认。

控制调用返回`NONE/CHECK/START/STOP`，只描述调用者必须处理的动作，函数本身不执行它们。所有时间单位为单调时钟毫秒，不传墙上时间。调用必须串行化。

1. `sp_init`：OFFLINE，默认单音15秒，不自动应用或发射。
2. **只有IO适配层验证实际工程身份及本次新鲜心跳后**，才能调用`sp_link`。0x71返回本身不是授权。
3. `CHECK`：适配层检查当前boot、源文件SHA、guard、RF配置/原接线许可及清理状态，保存`check_generation`。完成时回传同代`sp_check_done`。3秒无结果FAULT。
4. `START`：保存`run_generation`及active快照。只可启动当前受guard约束的固定预设，使用已检查文件和时长；不得将触屏文本拼进shell。
5. 只有**本次拥有的子进程**返回`CYCLIC_PUSH_SUBMITTED`后，带同代号调用`sp_submitted`，才转RUNNING。3秒未确认要求STOP并锁定故障。
6. `STOP`：适配层立即请求停止它所拥有的子进程，等待guard清理并验证DMA释放/DDS零源；确认后才调用`sp_finished(run_generation,clean,now)`。不能凭kill成功、进程消失或旧日志传clean=1。错误清理锁定FAULT，不自动重启。

CHECK/START的代号分别保存，不能用后来的代号替换旧异步回执。RUN回执不可仅依赖可复用的PID。旧代回执被忽略。心跳间隔计划500ms，2.5秒过期，重连清掉已应用状态；活动任务先停止，重连不恢复发射。调用者应至少每100ms执行`sp_tick`，并在解析错误、串口错误、启动/休眠回包及页面失配时使链接失效。

活动中改信号或时长请求STOP，只改变下次选择，不改当前active快照；必须清理完重新应用、开始。停止不受250ms去抖限制。正常发射也受时长+2秒的控制层保护，guard自身的时限仍独立生效。FAULT只能经明确重新初始化/重新核验恢复，不通过重连或点开始清除。

## 尚未实现的IO适配层

UART打开/termios恢复、工程身份和新鲜心跳事务、真实guard子进程管理、SHA与配置检查、日志清理验证、屏幕状态命令下发均待接入。`LINK/CHECKED/SUBMITTED/FINISHED`回放指令是测试输入，不能对不可信串口直接暴露。

UART设备须按独立EMIO UART0身份验证，禁止复用电脑调试ttyPS0。沿用P201 UART候选README的拒绝条件；当前候选仍不可部署。不要因本模块通过ARM自检就认定排针已可用。实际屏幕型号记录为`TJC4827T143_011C_P20`；官方`_I_P20`参考不能自动视为同一实物。

## 可重复检查

在项目根目录使用`.venv/Scripts/python.exe`运行：

```text
experiments/p63_build_panel_logic.py
experiments/p63_build_panel_wire.py
experiments/p63_render_panel_preview.py
```

前两项使用WSL gcc与已有ARM工具链，检查结果写新建results目录；不连接板卡。板上RAM自检另由`p63_board_logic_selftest.py --build-report <本次report.json>`执行，只运行已核验二进制`--selftest`，使用调试串口，保持真实RF停止。

`pw_number`只有在NUMBER且长度4时返回1，并写入调用者提供的uint32；不要把带FF的数值回包按结束符盲拆。未知回包不是支持承诺，需要按对应官方协议扩展及复测。
