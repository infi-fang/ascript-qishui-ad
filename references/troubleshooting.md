# AScript iOS 排障手册

本次从零跑通刷广告脚本时遇到的全部问题与解法。按「症状 → 根因 → 解决」组织。
遇到任何失败先对照本表定位，再执行对应命令。

## 速查表

| 症状 | 根因 | 解法 |
|---|---|---|
| exe 提示「不够信任」/ SmartScreen 拦截 | 官方激活工具未签名，无信誉 | 右键属性解除锁定 / 更多信息→仍要运行；来源核验为 `airscript.oss-cn-hangzhou.aliyuncs.com` |
| 挂载镜像失败：`lookup raw.githubusercontent.com: no data` | 路由器 DNS 污染成 `0.0.0.0` | 改 hosts 指向真实 IP（见下） |
| iOS 27 隧道未就绪：端口 `60105` 连接被拒 | 写 `selfIdentity.plist` 被 `Access denied` | 删旧 plist + 管理员身份运行激活工具 |
| App 显示地址但 `9096` 端口不通 | 设备服务开关未真正启动 HTTP 服务 | App「开发者」页关闭再重开设备服务 |
| 电脑上 `curl` 设备返回 502 | 系统代理环境变量劫持本地请求 | 清除 `HTTP_PROXY` 等环境变量；`device.py` 已自动处理 |
| 上传后设备 `__init__.py` 只有 279 字节 | 工程创建时的默认模板覆盖了上传文件 | 重新上传主脚本（`device.py deploy` 会自动校验并重试） |
| 脚本停在等待、不进广告 | 原版主循环从未调用进广告函数 | 已修复：第一轮主动调用 `wait_for_mian_button()` |

---

## 1. 激活工具 Windows 信任问题

**症状**：`ascript-ios-active-v4.2.exe` 报「Windows 已保护你的电脑」/「不够信任」。

**根因**：官方激活工具没有大厂数字签名，SmartScreen 按「未知发布者」拦截，非病毒。

**核验来源**（确认安全后再放行）：
```powershell
Get-Item -Path $f -Stream *                      # 看 Zone.Identifier 的 HostUrl
Get-AuthenticodeSignature -FilePath $f           # 预期 NotSigned
(Get-FileHash $f -Algorithm SHA256).Hash
```
本次文件来源 `airscript.oss-cn-hangzhou.aliyuncs.com`（官方 OSS），SHA256 `60775F1531577A62FDF87F57E9A43F06BFDA1694B26554D657A7C0966839A008`。

**解决**：
- `Unblock-File -Path $f` 移除网络锁定标记。
- 仍弹蓝窗则点「更多信息」→「仍要运行」。
- 不建议全局关闭 SmartScreen / 智能应用控制（智能应用控制关闭后无法重装系统外恢复）。

## 2. GitHub raw DNS 污染（挂载镜像失败）

**症状**：
```
挂载镜像失败: ... Get "https://raw.githubusercontent.com/.../BuildManifest.plist":
dial tcp: lookup raw.githubusercontent.com: getaddrinfow: The requested name is valid, but no data of the requested type was found.
```

**根因**：路由器把 `raw.githubusercontent.com` 解析成 `0.0.0.0`。激活工具是 Go 程序，直读系统 DNS、不走代理，因此失败。真实 IP 为 `185.199.108.x` 段。

**诊断**：
```bash
nslookup raw.githubusercontent.com     # 显示 0.0.0.0 = 被污染
ping -n 1 raw.githubusercontent.com
```

**解决 A — 改 hosts（需管理员）**：
写一个 **CRLF 换行** 的 bat（`fix-github-hosts.bat`），以管理员运行，写入：
```
185.199.110.133 raw.githubusercontent.com
```
然后 `ipconfig /flushdns`。
注意：GitHub raw 有 4 个 IP（`.108/.109/.110/.111`），哪个能通会波动，用 curl 逐一测，选当前 HTTP 200 的。
验证要用 `ping` 或 `python socket.gethostbyname`，**不能用 nslookup**（nslookup 不读 hosts）。

**解决 B — 绕过下载（本次最终采用，更稳）**：
国内镜像 `https://ghfast.top/<原始raw URL>` 可稳定秒下。手动把 5 个 Cryptex 文件下到工具缓存目录：
```
C:\Users\admin\Downloads\devimages\ddi-cryptex-<build>\Restore\
  BuildManifest.plist
  Image.dmg
  Image.dmg.trustcache
  Image.dmg.cryptex_info
  Image.dmg.root_hash
```
下载后用清单里的 SHA-384 校验每个文件完整性。工具启动时命中本地文件，彻底跳过 GitHub。

## 3. iOS 27 隧道未就绪（selfIdentity.plist 权限）

**症状**：
```
iOS 27 需要隧道连接，隧道未就绪 ... TunnelInfoForDevice: ...
http://127.0.0.1:60105/tunnel/<UDID>: connectex: No connection could be made
```
日志 `ascript-ios-active.log` 末尾：
```
tunnel: failed to create pair record manager:
createSelfIdentity: failed to open file for writing:
open selfIdentity.plist: Access is denied.
```

**根因**：旧 `selfIdentity.plist`（在 `Downloads\`）状态异常或权限不足，隧道服务无法启动，60105 端口无人监听。与 USB/信任无关（工具已能读到 UDID 即证明 USB 正常）。

**解决**：
1. 关闭残留激活工具进程。
2. 删除 `C:\Users\admin\Downloads\selfIdentity.plist`。
3. **以管理员身份**重新运行 `ascript-ios-active-v4.2.exe` 并点激活。
4. 成功标志：手机 AScript-WDA 显示 `Automation Running`。

> 手机重启后需重新激活。

## 4. 设备服务端口 9096 未监听

**症状**：手机 AScript 显示 `192.168.2.97:9096`，但电脑连不上；全端口扫描只有 `10102`（WDA WebSocket）、`62078`（lockdown），没有 9096。

**根因**：AScript App 的「设备服务」HTTP 服务没真正起来。10102 开着只说明 App 进程活着。

**解决**：
1. 打开 AScript App →「开发者」页。
2. **关闭**「设备服务」开关，等 2 秒。
3. **重新打开**，确认显示 `192.168.x.x:9096`。
4. App 保持前台、不锁屏。
5. 电脑执行 `python scripts/device.py doctor`，端口显示 OPEN 即成功。

> 官方默认端口是 `9096`（用户容易把 `9069` 看错）。以 App 实际显示为准。

## 5. 代理导致本地设备 502

**症状**：`curl http://192.168.2.97:9096/` 返回 502，但端口实际是开的。

**根因**：系统代理环境变量把本地网段请求也代理出去了。

**解决**：`scripts/device.py` 已在启动时清除 `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` 等并设 `NO_PROXY=*`，用它就不会遇到此问题。若手工 curl，加：
```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy NO_PROXY="*" curl ...
```

## 6. 上传后主脚本被模板覆盖

**症状**：上传 37KB 的 `__init__.py` 后，设备端 `get_project_files` 显示只有 279 字节。

**根因**：`create_project` 时自动生成的默认模板在首次上传后覆盖了文件。

**解决**：重新上传一次即可。`device.py deploy` 内置了校验+自动重试：比较设备端与本地字节数，不一致则重传。

## 7. 截图定位「免」字坐标

屏幕真实分辨率为 `1206×2622`。用设备端 OCR 定位：
```bash
python scripts/device.py eval --code "import json
from ascript.ios.system import screen_size
from ascript.ios.screen import Ocr
w,h=screen_size()
Ocr.set_engine('paddle')
r=Ocr.paddleocr(rect=[int(w*0.6),0,w,int(h*0.15)])
_result=json.dumps({'w':w,'h':h,'ocr':str(r)})"
```
本次「免」字识别到 `(898, 252)`，置信度 0.98。手动点击：
```bash
python scripts/device.py click 898 252
```

## 8. UAC 静默提权说明

若系统 `ConsentPromptBehaviorAdmin=0`，右键「以管理员身份运行」**不会弹 UAC 窗口，直接提权**——窗口一闪而过是正常现象，不代表失败。判断依据是脚本写的日志文件（如 `hosts-fix-result.log`），而不是看有没有弹窗。

另外：Windows bat 必须是 **CRLF 换行**，纯 LF 会导致 cmd.exe 解析 `if (...)` 块错乱、窗口闪退。
