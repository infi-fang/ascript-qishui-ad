#!/usr/bin/env python3
"""AScript iOS device operator (CLI).

Encapsulates every step of driving an AScript-enabled iPhone from a Windows PC:
connect, deploy, run, stop, log, screenshot, tap and arbitrary eval.

Why a wrapper exists:
  * Each Python process is independent -- connection state does not persist.
    Every command therefore connects first, then acts.
  * Local device HTTP is often hijacked by system proxy env vars (returns 502).
    This script strips proxy variables up front so 192.168.x.x is reached directly.
  * Deploying means uploading the bundled project (assets/project) to the device.

Usage:
  python device.py <command> [options]

Commands:
  doctor               Diagnose PC IP, device reachability, ports, ascript-mcp install
  status               Connect and print device status
  scan                 Scan LAN for AScript devices on the configured port
  deploy               Upload bundled project (__init__.py + res/img) to device
  run                  Run the deployed project
  stop                 Stop the running project
  logs                 Fetch run log (optionally filter for key events)
  shot                 Capture screenshot to a local file
  click                Tap screen coordinates on device
  eval                 Execute Python code inside the device's AScript runtime
  all                  One shot: deploy -> run -> fetch startup log

Config is read from ../device_config.json (host, port, project); CLI flags override.
"""

import argparse
import base64
import json
import os
import socket
import sys
from pathlib import Path

# --- Strip proxy env vars so local LAN device HTTP is never routed through a proxy ---
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "device_config.json"
PROJECT_DIR = SKILL_DIR / "assets" / "project"

DEFAULTS = {"host": "192.168.2.97", "port": 9096,
            "project": "qishuiAScriptProject"}


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"[warn] config read failed: {exc}", file=sys.stderr)
    return cfg


def get_device():
    try:
        import ascript_mcp.device as dev
        return dev
    except ImportError:
        print("[error] ascript-mcp missing. Install: python -m pip install ascript-mcp psutil",
              file=sys.stderr)
        sys.exit(2)


def connect(dev, host, port):
    return dev.connect(host, port=port)


def print_logs(logs, only_key=False, limit=0):
    if not logs:
        print("(no logs)")
        return
    keys = ("轮", "领取成功", "领取奖励", "成功", "超时", "失败", "退出",
            "直播", "关闭", "检测到", "额度", "脚本", "步骤0", "阶段")
    shown = 0
    for item in logs:
        msg = str(item.get("msg", "")).strip()
        if only_key and not any(k in msg for k in keys):
            continue
        kind = {"e": "ERROR", "o": "OUT", "i": "INFO"}.get(item.get("type", ""), "LOG")
        print(f"[{kind}] {msg}")
        shown += 1
        if limit and shown >= limit:
            break


def cmd_doctor(args, cfg):
    dev = get_device()
    host, port = args.host or cfg["host"], args.port or cfg["port"]
    print("=== AScript device doctor ===")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        print(f"PC LAN IP      : {s.getsockname()[0]}")
        s.close()
    except Exception as exc:
        print(f"PC LAN IP      : unavailable ({exc})")
    try:
        ip = socket.gethostbyname(host)
        print(f"Device DNS     : {host} -> {ip}")
    except Exception as exc:
        print(f"Device DNS     : {host} -> failed ({exc})")
    s = socket.socket()
    s.settimeout(2)
    rc = s.connect_ex((host, port))
    s.close()
    print(f"Port {port:<16}: {'OPEN' if rc == 0 else 'CLOSED (rc=' + str(rc) + ' -- re-enable 设备服务 on iPhone)'}")
    try:
        st = dev.get_device_status()
        print(f"Device status  : {st}")
    except Exception as exc:
        print(f"Device status  : error ({type(exc).__name__}: {exc})")
    print(f"MCP package    : {getattr(dev, '__file__', 'ascript_mcp.device')}")


def cmd_status(args, cfg):
    dev = get_device()
    print(connect(dev, args.host or cfg["host"], args.port or cfg["port"]))
    print(dev.get_device_status())


def cmd_scan(args, cfg):
    dev = get_device()
    try:
        found = dev.scan_devices(port=args.port or cfg["port"])
        print(found if found else "No device found")
    except Exception as exc:
        print(f"scan failed: {type(exc).__name__}: {exc}")


def cmd_deploy(args, cfg):
    dev = get_device()
    project = args.project or cfg["project"]
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    if not PROJECT_DIR.exists():
        print(f"[error] bundled project missing: {PROJECT_DIR}", file=sys.stderr)
        sys.exit(3)

    main = PROJECT_DIR / "__init__.py"
    code = main.read_bytes()
    print(f"[deploy] main script: {len(code)} bytes -> {project}/__init__.py")
    print("  result:", dev.upload_file(project, "__init__.py", code))

    img_dir = PROJECT_DIR / "res" / "img"
    if img_dir.exists():
        for image in sorted(img_dir.glob("*.png")):
            data = image.read_bytes()
            rel = f"res/img/{image.name}"
            try:
                dev.upload_file(project, rel, data)
                print(f"  [ok] {rel} ({len(data)} bytes)")
            except Exception as exc:
                print(f"  [fail] {rel}: {type(exc).__name__}: {exc}")

    # Verify -- first upload can be overwritten by the auto-generated template.
    check = dev.download_file(f"~/modules/{project}/__init__.py")
    ok = len(check) == len(code)
    print(f"[verify] device size={len(check)} local size={len(code)} -> "
          f"{'OK' if ok else 'MISMATCH (re-upload required)'}")
    if not ok:
        print("  retrying upload...")
        dev.upload_file(project, "__init__.py", code)
        check = dev.download_file(f"~/modules/{project}/__init__.py")
        print(f"  retry verify: {len(check)} -> {'OK' if len(check) == len(code) else 'STILL MISMATCH'}")


def cmd_run(args, cfg):
    dev = get_device()
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    print("run:", dev.run_project(args.project or cfg["project"]))


def cmd_stop(args, cfg):
    dev = get_device()
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    print("stop:", dev.stop_project())


def cmd_logs(args, cfg):
    dev = get_device()
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    print_logs(dev.get_run_log(seconds=args.seconds),
               only_key=args.key, limit=args.limit)


def cmd_shot(args, cfg):
    dev = get_device()
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    shot = dev.screen_capture()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(shot.get("base64", "")))
    print(f"screenshot -> {out}")


def cmd_click(args, cfg):
    dev = get_device()
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    code = (
        "import json\n"
        "from ascript.ios.action import click\n"
        f"click({int(args.x)}, {int(args.y)})\n"
        "_result = json.dumps({'clicked': [%d, %d]})" % (int(args.x), int(args.y))
    )
    print("click:", dev.eval_python(code))


def cmd_eval(args, cfg):
    dev = get_device()
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    source = Path(args.file).read_text(encoding="utf-8") if args.file else args.code
    if source is None:
        print("[error] provide --code or --file", file=sys.stderr)
        sys.exit(3)
    print(dev.eval_python(source))


def cmd_all(args, cfg):
    """deploy -> stop old -> run -> startup log"""
    dev = get_device()
    project = args.project or cfg["project"]
    connect(dev, args.host or cfg["host"], args.port or cfg["port"])
    try:
        dev.stop_project()
    except Exception:
        pass
    code = (PROJECT_DIR / "__init__.py").read_bytes()
    dev.upload_file(project, "__init__.py", code)
    img_dir = PROJECT_DIR / "res" / "img"
    if img_dir.exists():
        for image in sorted(img_dir.glob("*.png")):
            try:
                dev.upload_file(project, f"res/img/{image.name}", image.read_bytes())
            except Exception:
                pass
    print("run:", dev.run_project(project))
    print_logs(dev.get_run_log(seconds=args.seconds), only_key=args.key)


def build_parser():
    cfg = load_config()
    p = argparse.ArgumentParser(description="AScript iOS device operator")
    p.add_argument("--host", default=None, help=f"device IP (config: {cfg['host']})")
    p.add_argument("--port", type=int, default=None, help=f"device port (config: {cfg['port']})")
    p.add_argument("--project", default=None, help=f"project name (config: {cfg['project']})")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="diagnose connectivity")
    sub.add_parser("status", help="connect and print status")
    sub.add_parser("scan", help="scan LAN for devices")
    sub.add_parser("deploy", help="upload bundled project to device")
    sub.add_parser("run", help="run project")
    sub.add_parser("stop", help="stop project")

    pl = sub.add_parser("logs", help="fetch run log")
    pl.add_argument("--seconds", type=int, default=10)
    pl.add_argument("--key", action="store_true", help="only key events")
    pl.add_argument("--limit", type=int, default=0)

    ps = sub.add_parser("shot", help="screenshot")
    ps.add_argument("--out", default=str(Path.home() / "Downloads" / "ascript_shot.png"))

    pc = sub.add_parser("click", help="tap coordinates")
    pc.add_argument("x", type=int)
    pc.add_argument("y", type=int)

    pe = sub.add_parser("eval", help="run Python inside device runtime")
    pe.add_argument("--code", default=None)
    pe.add_argument("--file", default=None)

    pa = sub.add_parser("all", help="deploy + run + startup log")
    pa.add_argument("--seconds", type=int, default=12)
    pa.add_argument("--key", action="store_true")
    return p


def main():
    args = build_parser().parse_args()
    cfg = load_config()
    handlers = {
        "doctor": cmd_doctor, "status": cmd_status, "scan": cmd_scan,
        "deploy": cmd_deploy, "run": cmd_run, "stop": cmd_stop,
        "logs": cmd_logs, "shot": cmd_shot, "click": cmd_click,
        "eval": cmd_eval, "all": cmd_all,
    }
    try:
        handlers[args.command](args, cfg)
    except Exception as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
