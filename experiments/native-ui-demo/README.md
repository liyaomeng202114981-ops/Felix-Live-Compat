# 原生 Linux 预览解耦演示

低成本的路线一前置演示：Linux Electron 窗口显示独立 Linux Python 进程生成的 320×180 RGBA 测试帧，目标 30 Hz。可缩放、最大化、还原，以及真正暂停／恢复测试子进程。它没有接入 Wine 或官方 Media SDK，不能据此声称伴侣已移植或测出与原版的性能改善。

帧通过 stdout 管道、Electron IPC 和 CPU 拷贝传递；单个最新帧槽及确认避免积累显示队列。本示例不是 DMA-BUF／GPU 零拷贝，也不访问桌面、声音、网络或账号。独立 UI 的动画只是活性提示，不是实际输出帧率；界面单独显示真实接收计数。

复用本机星火抖音的 Linux Electron 运行库，仅在私有临时目录硬链接／复制可执行文件并链接只读依赖。使用自己的 app、临时用户目录；不启动或改写星火版源码与 profile，不新增 Dock 图标。第三方运行库不复制进 Git，许可仍归其原作者。演示源码 BSD-3-Clause，署名 Felix Li with OpenAI Codex assistance。

```bash
/usr/bin/python3 -B experiments/native-ui-demo/run.py --output /path/to/private/demo-output
```

在桌面找到「Felix 原生 Linux 预览演示（独立测试）」。拖动边缘和最大化，点「暂停测试后端」后继续缩放，再恢复。普通关闭演示窗口即可结束生产者并清理临时运行目录。日常直播伴侣保持原样，不开播、不改音画／直连。

加 `--self-test` 执行自己的尺寸变化、暂停／恢复及帧号／UI 活性检查，并将脱敏结果和仅本演示窗口截图写入 output，然后退出。这是功能自检，不是物理呈现延迟或正式 A/B 基准。
