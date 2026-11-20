# Linux 界面到 Wine 官方 SDK 的最小原型

状态（2026-11-20）：**官方媒体服务初始化、版本查询、自有场景 A／B 渲染快照返回 Linux 均已通过**。连续视频、GPU 零拷贝、窗口采集和完整客户端 UI 迁移仍未实现，不加入 RC3.4 默认或发行包。

## 已验证链路

Linux Electron 39.2.7 窗口异步发起本地子查询，同版本 Windows Electron `36.4.0-rs.31.release.lynx41.32` 在私有 Wine 前缀加载官方 `MediaSDK_Client.node`，通过原协议初始化独立媒体服务，取得 SDK 版本 `13.3.5.7`。

原型创建 320×180 自有图片素材，经 SDK `image.Create`／`image.SetFile` 切换 A／B 场景，再用 SDK 的 `PreviewThumbnailSaveAs` 导出 PNG，返回 Linux 窗口。两张静态快照的全部 RGB 像素与各自 BMP 测试源一致；这不代表视频编码质量、物理呈现延迟或零拷贝性能通过。

当前窗口「Felix 原生 SDK 预览原型（快照）」执行一次真实图像测试，结束后保留 A／B 图像供缩放和切换。每轮结束时媒体宿主已经停止，页面不是连续视频预览。原先只读探针仍可用：它不初始化服务，所以读出的 false 状态不是后端不可用的证据。

本轮沿用此前独立接口实验的 Proton 副本（包含 0075 非致命状态原型），运行器在各配置对照中保持不变，没有与日常 RC3.4 原 GDI32 做新对照。不能将此结果直接当作现有发行包的新验收。[脱敏结果](results/20261120-initialization.json)

## 初始化失败如何定位

1. 原 Node 模式先成功加载插件及协议 helper，读取 12 个原生接口。
2. 初始宿主少 `graphicscapture=n`，误用 Wine 同名 DLL，报缺 TinyFramework 的 IsSupportedWINRT。仅补齐独立进程的 DLL 选择规则，没有改日常配置。
3. 改用带隐藏 HWND 的正常 Windows Electron 消息循环，按原程序配置 NV12／BT709、windowless view、NVENC／NVAPI 后，SDK 收到初始化请求并创建场景，但仍退出 `0xc0000409`。
4. SEH／DLL 加载记录将退出地址映射到 `metasecml.dll`，RVA `0x2c6525` 在其 `0x73a000` 映像内。只补空 signInfo 对象仍复现同一失败位置。
5. 原客户端会提供已安装包内的产品初始化参数。`product-context.js` 在内存读取并原样沿用对应配置，不复制配置值进源码、不输出值、不改检查。未提供账号／设备标识；补齐后初始化、服务存活和版本查询通过。当前证据支持此前宿主缺少正常产品上下文；没有分别量化各字段贡献，也不推广为所有 metasec 退出的原因。
6. CLI 的 A／B 像素检查及 Linux UI 图像解码自检通过，截图仅包含本测试页面。没有桌面共享、真实账号操作、音频采集或开播。

早期还有自有诊断脚本误用 type.create，已修正，不能归因于厂商接口缺失。简化 Node 的等待超时、完整宿主的服务崩溃、产品配置修复分阶段记录。直接调用 teardown 时参数不匹配的试验已移除；当前由有界、精确的 systemd 服务组回收自身进程，通用 SDK 优雅退出适配仍待实现。

## 源码与配置边界

| 文件 | 作用 |
| --- | --- |
| `probe.js` | 只读加载、接口及状态查询，无初始化或采集 |
| `sdk-loader.js` | 在内存去掉固定版本 bundle 的两个业务入口，仅加载 SDK helper；入口不匹配则拒绝 |
| `product-context.js` | 从已安装客户端读取原产品配置，仅在私有进程内使用，源码不含配置值 |
| `query.js` | 原上下文下的初始化、版本查询及可选 A／B 快照，不用于日常启动 |
| `run_host.py` | 私有宿主准备、独立进程环境、测试 BMP 及 22 秒服务上限 |
| `main.js`、`preload.js`、`index.html` | Linux 状态／快照界面，无任意命令入口 |

官方 bundle、插件和二进制由用户本机安装提供，不写入 Git。自有脚本采用 BSD-3-Clause，第三方源码及资源仍归其原作者。SDK 私有日志可能包含初始化配置值，不能上传。不存在关闭检查、伪造成功或向正式服务提交测试账号的步骤。

## 复跑

宿主仅接受已有私有 evidence 路径，禁止使用日常安装。`$isolated_root` 是已停止的独立安装副本，`$case` 为私有证据目录。

```bash
/usr/bin/python3 -B experiments/wine-sdk-bridge/run_host.py \
  --root "$isolated_root" --case "$case" --result status.json --probe-only

/usr/bin/python3 -B experiments/wine-sdk-bridge/run_host.py \
  --root "$isolated_root" --case "$case" --result preview.json --preview-test
```

仅初始化／查询版本时加 `--client-product-config`；`--preview-test` 自动沿用该配置。`--trace-seh` 仅记录独立宿主异常及 DLL 加载。`--empty-sign-info` 是保留的失败对照，不能代替原产品参数。

GUI 使用本机 0600 的 FELIX_SDK_BRIDGE_CONFIG JSON，字段为 runner、root、case、previewCase；后两者分别存只读及图像测试，避免覆盖同一运行中的脚本。使用 `native-ui-demo/run.py --app-dir experiments/wine-sdk-bridge --output "$case"` 打开原生窗口，关闭窗口会取消在途查询。测试结束后不常驻媒体 SDK，不操作日常实例。

## 后续与回退

下一步是持续帧流、时间轴、缩放中的连续更新、关闭清理及传输成本；GPU 共享和显式同步尚待实现。既有采集方向 DMA-BUF 成果不能当作 Linux 预览方向已经通过。完整前端复用及其他原生插件仍未验证。

不采用此实验或关闭测试窗口即可回退，原安装与原 Dock 不变。本轮未上传、发布或开播，也没有改动音画、直连或系统配置。
