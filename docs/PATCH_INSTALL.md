# 在已有安装上应用补丁（patch 模式）

## 适用场景

用户**已经装过一次本套件**（即已有 `runner/`、`prefix/`、`shorin-proton-wrapper`，
且前缀里装好了官方 Windows 客户端），只想更新兼容层，不再重新下载 runner、
不再重装客户端、不重建前缀。

```bash
tar --zstd -xf felix-live-compat-patch-*.tar.gz
cd Felix-Live-Compat
python3 -B tools/felix_live.py patch --root ~/Games/Felix-Live-Compat
```

`patch` 会刷新以下内容，并保留 runner、前缀与已安装客户端：

| 内容 | 说明 |
| --- | --- |
| `payload/` | 兼容层运行产物（DXVK 转发器、WGC 组件、动作代理、窗口流等） |
| `runner/files/...` | 匹配 runner 的 Wine 补丁模块（`wineserver`、`ntdll.so`、`wow64.dll`、`winex11.so`、`explorer.so`） |
| 前缀注入 | 把 payload 文件写进 `windows/system32`，重写 `wgc.reg` 注册表项与 DLL overrides |
| `launcher/tools`、`launcher/src` | 启动器与辅助进程（含拖拽缩放 helper） |
| 桌面入口 | 重新注册 `/usr/share/applications` 下的 `.desktop` 入口 |

## 不适用场景

- **只有系统 Wine（apt/dnf/发行版自带）**：本套件依赖 `patches/wine/0066–0075`
  的补丁运行时候选与匹配的 `wine-runtime` 模块，普通 Wine 无法在
  原地“打补丁”获得这些能力；
- **前缀里没有官方客户端**：patch 模式不会运行官方安装器，要求
  `Program Files (x86)/webcast_mate/直播伴侣 Launcher.exe` 已存在；
- **runner 版本不匹配**：`patch` 只校验 `runner/proton` 存在，不校验版本。
  跨大版本升级请走完整 `install`。

## 校验

```bash
python3 -B tools/felix_live.py launch --root ~/Games/Felix-Live-Compat --direct
# 启动后检查 helper 是否挂上:
grep -E '"attach"|"layout"' "$XDG_RUNTIME_DIR"/felix-live-compat-*/ui-resize.log
```

补丁模式是幂等的：可以重复执行，每次都会覆盖同为 kit 管理的文件。

## 回退

patch 模式不备份被覆盖的文件（`payload/`、wine 模块、`launcher/tools` 均可由
发行 tarball 重新提供）。需要彻底回退时卸载并重新 `install`。
