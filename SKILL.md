---
name: ascript-qishui-ad
version: "1.1.0"
display_name: opt project · 手机自动领奖助手
display_name_en: opt project - Phone Auto Reward Assistant
description: Drive an AScript-enabled iPhone from Windows to run the "watch ads for free listening time" automation on Qishui Music. Use when the user asks to 刷广告 / 刷汽水音乐 / 领免费听歌时长 / 运行或停止刷广告脚本 / 排查 AScript 设备连接与激活问题. Handles connect, deploy, run, stop, log, screenshot and device troubleshooting. Requires a Windows PC with ascript-mcp installed and an iPhone with AScript App + WDA activated, device service enabled, on the same LAN.
description_zh: 从 Windows 操控已激活的 AScript iPhone，运行汽水音乐「看广告领免费听歌时长」脚本。覆盖连接设备、部署工程、运行、停止、抓日志、截图及激活/连接排障。适用于「刷广告 / 刷汽水音乐 / 领免费时长 / 跑或停脚本」等请求。
description_en: Control an activated AScript iPhone from Windows to run the Qishui Music ad-watching automation. Covers device connect, deploy, run, stop, log, screenshot and activation/connection troubleshooting.
agent_created: true
---

# opt project · 手机自动领奖助手

## 概念澄清（务必先理解）

这个 skill **不是**跑在手机上的脚本本体，而是**从 Windows 电脑操控手机的控制台**：

- **真正的脚本**在 `assets/project/__init__.py`，是 AScript iOS 项目，只能运行在 iPhone 的 AScript App 里（依赖 `ascript.ios.*`，电脑 Python 没有这个库）。
- **本 skill 的作用**：把「连接设备 → 上传工程 → 运行 → 抓日志 → 排障」这套流程固化成一个命令行工具 `scripts/device.py`，让 AI 无需每次重写连接代码。
- 因此**手机必须在线、AScript 设备服务必须开启**，否则任何命令都无法执行。skill 不能替代这些前置条件。

## 前置条件（缺一不可）

### 一、要先安装的软件（官网，引导用户时直接给出）

**电脑端（Windows）**

| 软件 | 官网 | 安装要点 |
|---|---|---|
| Python 3.10+ | https://www.python.org/downloads/ | 安装时勾选「Add Python to PATH」 |
| ascript-mcp + psutil | https://pypi.org/project/ascript-mcp/ · 官方文档 https://www.ascript.cn/mcp | `pip install ascript-mcp psutil` |

**手机端（iPhone）**

| 软件 | 官网 | 安装要点 |
|---|---|---|
| 汽水音乐 | https://www.qishui.com/ | 目标 App；只认此官网，其他"下载站"多为仿冒 |
| AScript App + AScript-WDA | https://www.ascript.cn/ | 官网 iOS 免签安装，装完在 App 内激活 WDA |
| iOS 激活工具 ascript-ios-active.exe | https://www.ascript.cn/ | 来自官方 OSS `airscript.oss-cn-hangzhou.aliyuncs.com`；右键「以管理员身份运行」，SmartScreen 提示选「仍要运行」 |

### 二、装完后的状态检查
- 电脑：与手机在同一局域网，`python` 命令可用。
- 手机：AScript App 显示「已激活」。
- 手机：AScript「开发者」页 设备服务开关已打开，显示形如 `192.168.x.x:9096` 的地址。
- 手机：App 保持在前台、不锁屏。

> 用户是小白时，务必先把上面的官网链接发给他、确认软件装齐，再执行任何命令。前置条件不满足时先读 `references/troubleshooting.md`，里面有激活失败、DNS 污染、隧道、端口未监听等完整解决方案。

## 核心工作流

### 第 0 步：确认设备就绪

```bash
python scripts/device.py doctor
```

该命令输出：电脑 IP、设备 DNS 解析、`9096` 端口是否监听、设备状态。
若端口 `CLOSED`，让用户在手机 AScript「开发者」页 **关闭再重开设备服务**，然后重试。

### 第 1 步：部署并运行（最常用）

```bash
python scripts/device.py all --key
```

一键完成：停止旧进程 → 上传主脚本 + 4 张图片 → 运行 → 抓取启动日志（`--key` 只显示关键事件）。
看到「步骤0：主动寻找入口进入广告」「阶段三」等日志即为正常运行。

若只需单独操作，可拆开执行：

```bash
python scripts/device.py deploy     # 仅上传工程（会自动校验大小，防模板覆盖）
python scripts/device.py run        # 运行
python scripts/device.py logs --seconds 20 --key   # 抓日志
```

### 第 2 步：监控循环

脚本全自动循环；每轮约 30 秒。定期抓日志确认成功次数：

```bash
python scripts/device.py logs --seconds 25 --key
```

判断标准：出现「第 N 轮领取成功！累计成功次数 = N」。连续 10 轮无广告会自动退出（当日额度用完）。

### 第 3 步：停止

```bash
python scripts/device.py stop
```

## 设备地址变更

手机换网络后 IP 会变。更新 `device_config.json` 的 `host`（和 App 显示的 `port`），或在任意命令后加 `--host <IP> --port <端口>` 临时覆盖。

查找设备 IP：

```bash
python scripts/device.py scan
```

若扫描无结果，让用户在手机 AScript「开发者」页直接读取显示的地址。

## 其他命令

```bash
python scripts/device.py status              # 连接并打印状态
python scripts/device.py shot --out shot.png # 截图，确认当前界面
python scripts/device.py click 898 252       # 点击坐标（如手动点"免"字进广告）
python scripts/device.py eval --code "<python代码>"  # 在设备运行时执行代码
```

`eval` 的代码里必须用 `_result = ...` 赋值才有返回值，例如：

```python
import json
from ascript.ios.system import screen_size
w, h = screen_size()
_result = json.dumps({"w": w, "h": h})
```

## 脚本已内置的修复

`assets/project/__init__.py` 已在原仓库基础上修复过一个关键缺陷：原版主循环从未调用进入广告的函数，导致必须手动点第一个广告。现版本在**第一轮**主动调用 `wait_for_mian_button()` 点「免」字/解锁按钮进广告，之后「领取奖励」会自动进入下一轮，实现全自动。

## 合规与风险提示

- 该脚本通过自动化模拟「看广告领时长」，可能违反汽水音乐用户协议，存在账号风控（限流、封号）风险；仅在用户自己的设备与账号上使用，由用户自行承担。
- 涉及第三方 App 图像识别，平台 UI 改版后需更新 `res/img/` 模板图。
- 不要向他人分发或用于规模化牟利。

## 资源清单

- `scripts/device.py` — 设备操作 CLI（所有命令入口）。
- `device_config.json` — 设备 IP/端口/工程名配置。
- `assets/project/` — 要上传到手机的 AScript 工程（`__init__.py` + `res/img/` 4 张图）。
- `references/troubleshooting.md` — 激活、DNS、隧道、端口、上传等完整排障手册，**遇到任何失败先读它**。
