# P86 跨设备写作资料包（2026-10-28）

用户要求将完整交接提示词与相关文件整理成压缩包，用于另一台设备写项目总结文章。此任务只读取/复制电脑文件，没有板控、串口、RF、烧录或软件界面操作。

## 已生成

- 写作包：`C:/Users/project_user/Downloads/rf-signal-lab-writing-20261028T145926Z.zip`。
- 解压前的资料目录：`C:/Users/project_user/Downloads/rf-write-20261028T145926Z/rf-project`。
- 打包报告：`C:/Users/project_user/Downloads/rf-write-20261028T145926Z/report.json`。
- 文件数 13180；压缩包大小 185912628 字节；SHA256 `5065adf3c89f5473e0da902681b417ba77f0b863539089aacaad2cba78486c47`。
- ZIP 成员名唯一、CRC、全部 manifest 成员的字节数与 SHA256 核验通过；Downloads 副本 SHA 一致。

根目录提供使用说明、完整提示词、项目事实/限制、证据索引、文章结构和 P85 实际状态快照。project 保留工程相对路径，含全部 docs、相关源码/配置/测试、磁盘收集的 JSON/文本历史/绘图和精选完整原始证据/模型/小型检查点。大型重复旧包、工具安装器、许可证、虚拟环境、完整厂商资料与部分原始数据未纳入，逐文件清单见 omitted-files.json。

## 内容边界

包内明确 PS/PL/PC 分工、受控有线真实RF范围、三类分类与新旧算法成绩区分、99% ROI 和数字相对功率的量纲，避免写作夸大。P81 完整人工验收保留；P85 服务实际已 partial 结束，记录三类自然任务但没有主动 STOP，且本轮完整 RX 归档未完成。P84 未归档 RAM 随新boot丢失，主机日志/照片保留。

这不是完整聊天导出或可直接换机烧录/运行的完整迁移包。包内 project/START-HERE.md 副本添加了“历史运行状态”提示，原工程文件未被改写；original SHA 见 source-state.json。

首次试打包在原工程深路径内遇到 Windows MAX_PATH，未产生通过声明；改用 Downloads 短目录后生成并验证上述最终包。原失败暂存目录保留，不作为交付。
