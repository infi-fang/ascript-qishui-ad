# -*- coding: utf-8 -*-
"""
opt project · 自动看广告小助手（小白友好版）
====================================================
它会帮你做这 5 件事：
  1. 打开 App
  2. 顺手关掉挡路的会员弹窗
  3. 找到右上角的"免"字并点进去
  4. 等广告倒计时结束
  5. 自动点领取，拿时长

你不需要懂代码：手机上装好 App、打开"设备服务"，电脑上跑一条命令就行。

小提示：脚本靠"看屏幕上的字"来找按钮，所以 App 界面文字变了可能需要更新识别图。
"""

import time
import traceback

# ============== 基础模块导入 ==============
from ascript.ios import action  # type: ignore
from ascript.ios.system import R, app_start, screen_size, notify  # type: ignore
from ascript.ios.screen import Ocr, FindImages  # type: ignore
from ascript.ios import node # type: ignore
from ascript.ios.node import Selector # type: ignore


# ============== 全局配置 ==============

# 要操作的 App。一般不用改；想换别的 App 才动这两行（第二行更准确，优先用）
APP_NAME = "汽水音乐"
APP_BUNDLE_ID = "com.soda.music"

# 循环控制（多久领一次、最多领多少次）
MAX_LOOP_COUNT = 50         # 最多领多少次，防止一直跑
LOOP_INTERVAL = 3           # 每轮之间歇几秒

# 文字识别用哪个引擎。iOS 16 以上用 vision 就行
OCR_ENGINE = "vision"       # 可选 vision / paddle / mlkit，一般不用改

# 屏幕上去哪找按钮（按屏幕比例算，换手机也能用）
# 右上角"免"字大概出现的范围
REGION_TOP_RIGHT = None     # 运行时根据屏幕尺寸动态计算
# 整个屏幕
REGION_FULL = None
# 有没有准备"关闭直播间"的参考图（启动时自动检查一次）
HAS_LIVE_ROOM_TEMPLATE = False


# ============== 工具函数 ==============

def log(msg: str):
    """在控制台打印一条带时间的提示，方便你看脚本在干嘛"""
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{ts}] {msg}")


def safe_click(x: int, y: int, desc: str = ""):
    """
    点一下屏幕，并把这一步记进日志。点失败也不会让脚本崩掉。
    """
    try:
        log(f"点击 [{desc}] -> ({x}, {y})")
        action.click(x, y)
        time.sleep(0.8)  # 点击后等待界面响应
        return True
    except Exception as e:
        log(f"点击失败 [{desc}]: {e}")
        return False


def click_center():
    """点屏幕正中间（用来关掉挡路的弹窗）"""
    w, h = screen_size() or (0, 0)
    if w > 0 and h > 0:
        safe_click(w // 2, h // 2, "屏幕中心")
    else:
        safe_click(200, 400, "默认中心")


def init_regions():
    """先量一下手机屏幕多大，再算好去哪找按钮，顺便检查参考图在不在"""
    global REGION_TOP_RIGHT, REGION_FULL, HAS_LIVE_ROOM_TEMPLATE
    w, h = screen_size() or (1080, 1920)
    log(f"手机屏幕大小：{w} × {h}")
    # 右上角那一块：横向 60%~100%，纵向 0%~20%
    REGION_TOP_RIGHT = [int(w * 0.6), 0, w, int(h * 0.2)]
    REGION_FULL = [0, 0, w, h]
    # 看看"关闭直播间"的参考图在不在
    import os as _os
    template_path = R.img("img_zhibojian-close01.png")
    HAS_LIVE_ROOM_TEMPLATE = _os.path.exists(template_path)
    log(f"关闭直播间参考图：{'✅ 找到了，优先用它' if HAS_LIVE_ROOM_TEMPLATE else '❌ 没找到，改用看文字的方式'}")


# ============== 第 1 步：打开 App ==============

def launch_app() -> bool:
    """打开 App。发出指令就立刻往下走，好马上盯住开屏广告"""
    log("=" * 50)
    log("第 1 步：打开 App")
    try:
        if APP_BUNDLE_ID:
            ok = app_start(bundle_id=APP_BUNDLE_ID)
        else:
            ok = app_start(name=APP_NAME)
        if ok:
            log("已发出打开指令，马上开始盯着开屏广告，看到“跳过”就点")
            return True
        else:
            log("自动打开没成功，我试着在桌面上找图标点开")
            return try_click_app_icon()
    except Exception as e:
        log(f"打开 App 时出了点小状况：{e}")
        return try_click_app_icon()


def try_click_app_icon() -> bool:
    """备用方案：在桌面上找到图标，点它打开"""
    icon_path = R.img("qishuiyinyue.png")
    log("在桌面上找 App 图标...")
    try:
        for attempt in range(3):
            pos = FindImages.find(icon_path, confidence=0.8)
            if pos:
                return safe_click(pos["center_x"], pos["center_y"], "App 图标")
            log(f"  第 {attempt+1} 次没找到图标，再找找...")
            time.sleep(1)
        log("没找到图标，请确认桌面上有没有这个 App。")
        return False
    except Exception as e:
        log(f"找图标时出了点小状况：{e}")
        return False


# ============== 第 2 步：清理挡路弹窗 ==============

# 看到这些字样的弹窗就试着关掉
POPUP_KEYWORDS = [
    "续费会员", "会员享专属", "开通会员", "立即开通",
    "看视频领取", "领取更多时长", "看视频得",
   
]

# 弹窗上"关闭"按钮可能写的字
CLOSE_KEYWORDS = [
    "关闭", "叉", "×", "✕", "✖",
    "取消", "以后再说", "稍后", "暂不", "跳过",
]

# ============== 第 1 步补充：跳过开屏广告 ==============

# 开屏广告上"跳过"按钮常写的字
SPLASH_SKIP_KEYWORDS = [
    "跳过广告", "跳过", "跳过广告 ",
]


def skip_splash_ad(timeout=5) -> bool:
    """
    刚打开 App 时，盯住右上角，看到"跳过"就点掉。
    只在右上角一小块区域找，又快又准。位置按屏幕比例算，换手机也能用。
    """
    log("第 1 步补充：盯着开屏广告，看到“跳过”就点")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # "跳过"按钮一般在右上角这一小块
    rect_skip = [int(w * 0.80), int(h * 0.06), int(w * 0.97), int(h * 0.10)]

    deadline = time.time() + timeout
    scan_count = 0

    while time.time() < deadline:
        scan_count += 1
        try:
            # 在那一小块区域里找"跳过"两个字
            results = Ocr.paddleocr(rect=rect_skip, pattern=r"跳过")
            if results and isinstance(results, list) and len(results) > 0:
                for item in results:
                    cx = item.get("center_x", 0)
                    cy = item.get("center_y", 0)
                    if cx > 0 and cy > 0:
                        text = item.get("text", "")
                        conf = item.get("confidence", 0)
                        log(f"  找到“跳过”了（第 {scan_count} 次查看，把握 {conf:.0%}）→ 点掉")
                        action.click(cx, cy)
                        time.sleep(0.2)
                        return True
        except Exception as e:
            log(f"  第 {scan_count} 次查看时出了点小状况：{e}")

        time.sleep(0.1)
    log(f"  看了 {scan_count} 次，没有开屏广告要跳过，继续往下")
    return False


def ocr_find_text(keywords, rect=None, mode=None, timeout=0):
    """
    在屏幕上找这些字，找到第一个就告诉你它在哪
    找不到就返回空
    """
    engine = mode or OCR_ENGINE
    start = time.time()
    while True:
        try:
            # 一个一个关键词试着找
            for kw in keywords:
                result = Ocr.find(kw, rect=rect, mode=engine)
                if result:
                    log(f"  找到目标文字“{result.get('text', '')}”，位置在 ({result.get('center_x', 0)}, {result.get('center_y', 0)})")
                    return result
        except Exception as e:
            log(f"  看屏幕时出了点小状况：{e}")
        # 超时判断
        if timeout <= 0 or (time.time() - start) >= timeout:
            return None
        time.sleep(0.8)


def ocr_find_mid_first(keywords, mode=None):
    """
    弹窗按钮一般在屏幕中间，所以先找中间，找不到再找全屏。
    这样不会误点到顶部状态栏上的小字。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    mid_rect = [0, int(h * 0.2), w, int(h * 0.85)]
    engine = mode or OCR_ENGINE
    try:
        for kw in keywords:
            r = Ocr.find(kw, rect=mid_rect, mode=engine)
            if r:
                log(f"  在屏幕中间找到“{r.get('text','')}” ({r.get('center_x',0)},{r.get('center_y',0)})")
                return r
        for kw in keywords:
            r = Ocr.find(kw, rect=REGION_FULL, mode=engine)
            if r:
                log(f"  在屏幕上找到“{r.get('text','')}” ({r.get('center_x',0)},{r.get('center_y',0)})")
                return r
    except Exception as e:
        log(f"  找弹窗按钮时出了点小状况：{e}")
    return None


def paddle_find_first(pattern, rect, log_label=""):
    """
    在指定的一小块区域里找某个字，找到就返回它的位置。
    只看小块区域，所以又快又准。
    """
    try:
        results = Ocr.paddleocr(rect=rect, pattern=pattern)
        if results and isinstance(results, list):
            for item in results:
                cx = item.get("center_x", 0)
                cy = item.get("center_y", 0)
                if cx > 0 and cy > 0:
                    if log_label:
                        log(f"  {log_label}：找到“{item.get('text','')}”，把握 {item.get('confidence',0):.0%} ({cx},{cy})")
                    return item
    except Exception as e:
        log(f"  找字时出了点小状况：{e}")
    return None


# 看到这些按钮要直接点，不要关掉弹窗（这些才是我们想要的）
PRIORITY_CLICK_KEYWORDS = ["领取奖励", "领取成功", "立即领取", "确认领取"]


def close_membership_popup() -> bool:
    """
    关掉"开通会员"的弹窗（这是唯一会挡路的弹窗）。
    认准底部"元开通"几个字，然后点弹窗外面把它关掉。
    不用右滑，右滑会把 App 切到后台。
    返回：有没有真的关掉弹窗。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 底部那一条，按屏幕比例算，换手机也能对准
    bottom_rect = [int(w * 0.044), int(h * 0.877), int(w * 0.953), int(h * 0.963)]
    try:
        results = Ocr.paddleocr(rect=bottom_rect, pattern=r"元开通")
        if results and isinstance(results, list) and len(results) > 0:
            item = results[0]
            log(f"  发现开通会员弹窗（写着“{item.get('text','')}”）→ 点外面关掉")
            # 点弹窗上方的空白处，把它关掉
            try:
                action.click(int(w * 0.5), int(h * 0.30))
            except Exception as e:
                log(f"  关弹窗时出了点小状况：{e}")
            time.sleep(1.2)
            return True
    except Exception as e:
        log(f"  检查弹窗时出了点小状况：{e}")
    return False

# 兼容老版本的叫法，不用管
check_and_back_from_membership_page = close_membership_popup


def check_and_close_thirdparty_download() -> bool:
    """
    有时领完奖会跳到一个下载别的 App 的页面，这里负责关掉它回到主界面。
    认准左上角的"完成"按钮点一下就行。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 左上角"完成"按钮大概在这一块
    rect_done = [int(w * 0.02), int(h * 0.075), int(w * 0.19), int(h * 0.115)]
    try:
        results = Ocr.paddleocr(rect=rect_done, pattern=r"完成")
        if results and isinstance(results, list) and len(results) > 0:
            item = results[0]
            cx = item.get("center_x", 0)
            cy = item.get("center_y", 0)
            if cx > 0 and cy > 0:
                log("  跳到下载页面了，点左上角“完成”关掉")
                safe_click(cx, cy, "'完成'按钮")
                time.sleep(1.0)
                return True
    except Exception as e:
        log(f"  检查下载页面时出了点小状况：{e}")
    return False


def dismiss_popups(max_rounds=3) -> int:
    """
    把挡路的会员弹窗清掉，其他弹窗先不管。
    返回：一共关掉了几个弹窗。
    """
    log("第 2 步：看看有没有挡路的弹窗，有就关掉")
    handled = 0
    for _ in range(max_rounds):
        if close_membership_popup():
            handled += 1
            time.sleep(1.0)
            continue
        break
    if handled == 0:
        log("  没有挡路的弹窗，继续往下")
    log(f"弹窗处理完毕，一共关了 {handled} 个")
    return handled


# ============== 第 3 步：找到入口，进入广告 ==============


def light_background_cleanup() -> bool:
    """
    顺手看一眼有没有会员弹窗，有就关掉。只看一小块区域，很快，不耽误事。
    """
    return close_membership_popup()


def _detect_membership_popup(rect_pay) -> bool:
    """内部小助手：看看底部有没有会员弹窗。有就返回 True。"""
    try:
        results = Ocr.paddleocr(rect=rect_pay, pattern=r"元开通")
        return bool(results and isinstance(results, list) and len(results) > 0)
    except Exception:
        return False


def wait_for_mian_button(timeout=60, allow_mian=True) -> bool:
    """
    找进入广告的入口，找到就点进去。
    第一轮会同时找"立即解锁"弹窗和右上角的"免"字；
    后面的轮次只找"立即解锁"弹窗（因为"免"字只有刚打开 App 时才有）。

    timeout: 最多等几秒（填 0 表示只看一眼就走）
    返回: 有没有成功点进广告
    """
    if allow_mian:
        log("第 3 步：找进广告的入口（先找“立即解锁”，再找“免”字）")
    else:
        log("第 3 步：找进广告的入口（找“立即解锁”）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    rect_mian = [int(w * 0.65), int(h * 0.04), int(w * 0.92), int(h * 0.12)]
    rect_unlock = [int(w * 0.029), int(h * 0.52), int(w * 0.981), int(h * 0.982)]
    rect_pay = [int(w * 0.044), int(h * 0.877), int(w * 0.953), int(h * 0.963)]

    deadline = time.time() + timeout if timeout > 0 else 0
    check_count = 0
    last_err_log = 0.0
    last_cleanup = 0.0
    CLEANUP_INTERVAL = 8
    REVERIFY_WAIT = 0.7

    while True:
        check_count += 1

        # 先找"立即解锁 / 立即领取"这种弹窗按钮
        unlock_hit = None
        try:
            results = Ocr.paddleocr(rect=rect_unlock, pattern=r"立即(解锁|领取)")
            if results and isinstance(results, list) and len(results) > 0:
                item = results[0]
                cx = item.get("center_x", 0)
                cy = item.get("center_y", 0)
                if cx > 0 and cy > 0:
                    unlock_hit = (item, cx, cy)
        except Exception as e:
            if time.time() - last_err_log > 5:
                log(f"  看屏幕时出了点小状况：{e}")
                last_err_log = time.time()

        if unlock_hit is not None:
            item, cx, cy = unlock_hit
            text = item.get("text", "")
            conf = item.get("confidence", 0)
            log(f"  找到“{text}”了（第 {check_count} 次查看，把握 {conf:.0%}）→ 点进去")
            safe_click(cx, cy, f"'{text}'按钮")
            time.sleep(1.5)
            return True

        # 只有在第一轮才找"免"字
        if allow_mian:
            mian_hit = None
            try:
                results = Ocr.paddleocr(rect=rect_mian, pattern=r"免")
                if results and isinstance(results, list) and len(results) > 0:
                    item = results[0]
                    cx = item.get("center_x", 0)
                    cy = item.get("center_y", 0)
                    if cx > 0 and cy > 0:
                        mian_hit = (item, cx, cy)
            except Exception as e:
                if time.time() - last_err_log > 5:
                    log(f"  看屏幕时出了点小状况：{e}")
                    last_err_log = time.time()

            if mian_hit is not None:
                item, cx, cy = mian_hit
                text = item.get("text", "")
                conf = item.get("confidence", 0)

                # 先看看有没有会员弹窗挡着：有的话多点几次，没有就点一次直接走
                has_popup = _detect_membership_popup(rect_pay)
                MAX_RETRY = 2 if has_popup else 1
                log(f"  找到“免”字了（第 {check_count} 次查看，把握 {conf:.0%}）({cx},{cy})")

                for attempt in range(1, MAX_RETRY + 1):
                    log(f"  第 {attempt} 次点“免”字 ({cx},{cy})")
                    safe_click(cx, cy, f"'免'字按钮(尝试{attempt})")

                    # 只有有弹窗/MAX_RETRY>1 时才验证是否生效，否则直接成功返回
                    if MAX_RETRY == 1:
                        log("  点成功了，已经进入广告")
                        time.sleep(1.0)
                        return True

                    # 多点几次的情况：看看"免"字是不是消失了
                    time.sleep(REVERIFY_WAIT)
                    verify_hit = None
                    try:
                        vr = Ocr.paddleocr(rect=rect_mian, pattern=r"免")
                        if vr and isinstance(vr, list) and len(vr) > 0:
                            vi = vr[0]
                            vx = vi.get("center_x", 0)
                            vy = vi.get("center_y", 0)
                            if vx > 0 and vy > 0:
                                verify_hit = (vx, vy, vi.get("confidence", 0))
                    except Exception:
                        verify_hit = None

                    if verify_hit is None:
                        log(f"  点成功了，“免”字消失了（第 {attempt} 次）")
                        time.sleep(0.8)
                        return True

                    vx, vy, vconf = verify_hit
                    log(f"  “免”字还在屏幕上，再点一次")

                log(f"  点了 {MAX_RETRY} 次都没反应，这轮先跳过")

        # 都没找到的话，每隔几秒顺手清一下弹窗
        now = time.time()
        if now - last_cleanup >= CLEANUP_INTERVAL:
            try:
                light_background_cleanup()
            except Exception as e:
                log(f"  顺手清理时出了点小状况：{e}")
            last_cleanup = now

        if timeout > 0 and time.time() >= deadline:
            log(f"  等了 {timeout} 秒还没找到入口，这轮先跳过")
            return False
        if timeout == 0:
            log("  看了一眼，没找到入口")
            return False
        time.sleep(0.2)


# ============== 第 4 步：等广告播完 ==============

COUNTDOWN_KEYWORDS = [
    "秒后可领取", "秒后领取", "秒后关闭", "秒后获得",
   ]


def check_and_click_continue_watching() -> bool:
    """
    点屏幕中间的"继续观看"按钮（不小心关掉广告时会弹出）。
    注意：屏幕底部也会有"继续观看"字样，那是诱导下载别的 App，绝对不能点。
    所以只看中间那一块。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 只看屏幕中间那一块，避开底部的诱导下载按钮
    rect_continue = [int(w * 0.07), int(h * 0.25), int(w * 0.93), int(h * 0.68)]
    item = paddle_find_first(r"继续观看", rect_continue, "继续观看(中间区)")
    if item:
        ok = safe_click(item["center_x"], item["center_y"], "继续观看(中间区)")
        if ok:
            time.sleep(2.5)
            return True
    return False


def wait_ad_countdown(timeout=30) -> bool:
    """
    在广告页面等它播完。广告有两种：
      1) 视频广告：倒计时结束就算完
      2) 直播间广告：没有倒计时，要先点右上角"×"关掉直播间
    不管哪种，最后都是等右上角出现"领取成功"。
    """
    log("第 4 步：等广告播完（视频和直播间都支持）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 右上角"领取成功"大概出现的位置
    rect_claim_top = [int(w * 0.55), int(h * 0.03), w, int(h * 0.14)]
    # 右上角倒计时文字的位置（只是显示给你看）
    rect_countdown = [int(w * 0.58), int(h * 0.045), int(w * 0.97), int(h * 0.09)]
    # 直播间画面一般在屏幕中下方
    rect_live_room = [int(w * 0.092), int(h * 0.609), int(w * 0.911), int(h * 0.786)]
    # 直播间右上角"更多直播"的位置，用来确认是不是直播间
    rect_more_live = [int(w * 0.694), int(h * 0.099), int(w * 0.971), int(h * 0.145)]
    # 左上角"关注"按钮，认不出"更多直播"时用它判断是不是直播间
    rect_follow = [0, int(h * 0.05), int(w * 0.56), int(h * 0.107)]
    # 直播间右上角"×"关闭按钮的位置
    rect_close_btn = [int(w * 0.619), int(h * 0.055), w, int(h * 0.10)]

    deadline = time.time() + timeout
    last_sec = -1
    checks = 0
    is_live_room_logged = False

    while time.time() < deadline:
        checks += 1

        # 先看"领取成功"出来了没有（广告播完就会出现）
        hit_claim = paddle_find_first(r"领取成功", rect_claim_top, "倒计时结束标志")
        if hit_claim:
            log("  广告播完了，“领取成功”出现了 → 去领奖")
            return True

        # 再看是不是直播间广告（这种要先关掉）
        if not is_live_room_logged:
            live_check = paddle_find_first(r"直播间", rect_live_room, "直播间检测")
            if live_check:
                log("  是直播间广告，先把它关掉")
                is_live_room_logged = True

        # 看右上角有没有"更多直播"，有的话就是直播间
        more_live_hit = paddle_find_first(r"更多直播", rect_more_live, "直播间识别")
        # 认不出"更多直播"时，看左上角有没有"关注"按钮来判断
        follow_hit = None
        if not more_live_hit:
            follow_hit = paddle_find_first(r"关注", rect_follow, "关注按钮(左上角)")

        if more_live_hit or follow_hit:
            if more_live_hit:
                log(f"  命中'更多直播' → 确认在直播间内，尝试点击关闭按钮...")
            else:
                log("  看到左上角的“关注”，确认是直播间，试着关掉它")
            close_clicked = False
            
            # 优先用准备好的参考图去找"×"按钮
            if HAS_LIVE_ROOM_TEMPLATE:
                try:
                    template_path = R.img("img_zhibojian-close01.png")
                    result = FindImages.find(template_path, rect=rect_close_btn)
                    if result:
                        cx = result.get("center_x", 0)
                        cy = result.get("center_y", 0)
                        conf = result.get("confidence", 0)
                        log(f"  用参考图找到了关闭按钮（把握 {conf:.0%}）→ 点掉")
                        safe_click(cx, cy, f"直播间关闭按钮(模板匹配,置信度={conf:.2f})")
                        time.sleep(1.5)
                        log("  关掉了，继续等“领取成功”出现")
                        close_clicked = True
                except Exception as e:
                    log(f"  参考图没匹配上，改用看文字的方式找")
            
            # 备用：直接看右上角有没有"×"符号
            if not close_clicked:
                log("  改用看文字的方式找关闭按钮...")
                close_hit = paddle_find_first(r"[×✕✖]", rect_close_btn, "关闭按钮OCR")
                if close_hit:
                    cx = close_hit.get("center_x", 0)
                    cy = close_hit.get("center_y", 0)
                    log(f"  找到“×”了 ({cx},{cy}) → 点掉")
                    safe_click(cx, cy, "关闭按钮(OCR)")
                    time.sleep(1.5)
                    log("  关掉了，继续等“领取成功”出现")
                    close_clicked = True

            # 最后备用：前面都找不到时，直接问系统有没有叫"关闭"的按钮
            if not close_clicked:
                try:
                    log("  再问问系统有没有“关闭”按钮...")
                    node = Selector().label("关闭").find()
                    if node:
                        # 这个按钮位置是固定的，直接点中心
                        cx = (1206 + 1253) // 2
                        cy = (194 + 239) // 2
                        log(f"  系统说找到了“关闭”按钮 → 点它 ({cx},{cy})")
                        safe_click(cx, cy, "关闭按钮(Selector,固定坐标)")
                        time.sleep(1.5)
                        log("  关掉了，继续等“领取成功”出现")
                        close_clicked = True
                    else:
                        log("  系统也没找到关闭按钮")
                except Exception as e:
                    log(f"  问系统时出了点小状况：{e}")

            if close_clicked:
                continue  # 关闭后继续循环，等待领取成功出现
            else:
                log("  没找到关闭按钮，这轮先跳过")

        # 最后看下倒计时还剩几秒，只是显示给你看
        cd_hit = paddle_find_first(r"秒后可领奖励", rect_countdown, "倒计时")
        if cd_hit:
            text = cd_hit.get("text", "")
            sec = None
            for ch in text:
                if ch.isdigit():
                    sec = int(ch)
                    break
            if sec is not None and sec != last_sec:
                log(f"  广告还有 {text}")
                last_sec = sec

        time.sleep(0.8)

    log(f"  等了 {timeout} 秒还没看到“领取成功”，这轮可能没广告可领")
    return False


# ============== 第 5 步：领取奖励 ==============

def claim_reward() -> int:
    """
    领奖就两步，很固定：
      第 1 步：点右上角的"领取成功"
      第 2 步：点弹出来的"领取奖励"
    点完会自动进入下一轮广告。
    只有等超时没找到按钮才算失败。

    返回值：1=两步都成功；0=超时没找到按钮
    """
    log("第 5 步：领奖（点“领取成功” → 点“领取奖励” → 自动进下一轮）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 右上角"领取成功"的位置
    rect_claim_top = [int(w * 0.55), int(h * 0.03), w, int(h * 0.14)]
    # 中间"领取奖励"按钮的位置，超出这个范围就不点，避免点错
    rect_reward_btn = [int(w * 0.13), int(h * 0.25), int(w * 0.87), int(h * 0.70)]

    # ========== 第一步：等并点右上角"领取成功" ==========
    log("  第 1 步：等右上角的“领取成功”出现...")
    hit_claim = None
    deadline1 = time.time() + 20  # 广告刚播完，这个按钮很快就会出现
    checks1 = 0
    while time.time() < deadline1:
        checks1 += 1
        hit_claim = paddle_find_first(r"领取成功", rect_claim_top, "领取成功(右上角)")
        if hit_claim:
            break
        time.sleep(0.35)
    if not hit_claim:
        log(f"  等了 20 秒还没看到“领取成功”，这轮放弃")
        return 0
    cx1 = hit_claim["center_x"]
    cy1 = hit_claim["center_y"]
    log(f"  找到“领取成功”了（把握 {hit_claim.get('confidence',0):.0%}）→ 点它")
    safe_click(cx1, cy1, "'领取成功'(右上角)")

    # ========== 第二步：点完"领取成功"，肯定会弹"领取奖励"对话框，等它出现并点击 ==========
    log("  第 2 步：等中间的“领取奖励”按钮出现...")
    time.sleep(0.6)  # 等弹窗动画播完再找
    hit_reward = None
    deadline2 = time.time() + 15  # 点完后 15 秒内弹窗肯定出来
    checks2 = 0
    while time.time() < deadline2:
        checks2 += 1
        hit_reward = paddle_find_first(r"领取奖励", rect_reward_btn, "领取奖励(弹窗)")
        if hit_reward:
            break
        time.sleep(0.35)
    if not hit_reward:
        log(f"  等了 15 秒还没看到“领取奖励”弹窗，这轮放弃")
        return 0
    cx2 = hit_reward["center_x"]
    cy2 = hit_reward["center_y"]
    log(f"  找到“领取奖励”了（把握 {hit_reward.get('confidence',0):.0%}）→ 点它，进下一轮")
    safe_click(cx2, cy2, "'领取奖励'(弹窗)")
    time.sleep(1.5)  # 给 App 一点时间跳到下一条广告

    log("  领到啦！马上进入下一轮")
    return 1


# ============== 主流程：按顺序把上面的步骤串起来 ==============

def run_ad_loop() -> int:
    """
    一直循环：等广告播完 → 领奖 → 自动进下一轮。
    每领到一次就记 1 次，最后告诉你一共领了多少。
    """
    log("\n" + "#" * 60)
    log("🎯 开始自动领奖啦！想停的话，在电脑上点停止就行")
    log("#" * 60)
    log("   第 1 轮脚本会自己点进广告，之后就全自动了，你不用管")
    success_count = 0
    round_idx = 0
    MAX_IDLE_ROUNDS = 10  # 连着 10 轮都没广告，就自动停（一般是当天领满了）
    idle_count = 0

    while True:
        round_idx += 1
        log(f"\n---- 第 {round_idx} 轮广告循环 ----")

        # 第 1 轮：脚本自己找入口点进广告。
        # 第 2 轮起，"领取奖励"会自动带进下一条广告，不用再找入口。
        if round_idx == 1:
            log("  第 1 轮：先自己找到入口，点进广告")
            try:
                entered = wait_for_mian_button(timeout=25, allow_mian=True)
                log(f"  找入口的结果：{'点进去了' if entered else '没找到入口，或者已经在广告里'}")
            except Exception as e:
                log(f"  找入口时出了点小状况：{e}")
            time.sleep(1)

        # 等这一轮广告播完（最多等 30 秒）
        got_ad = wait_ad_countdown(timeout=30)
        if not got_ad:
            idle_count += 1
            log(f"  第 {round_idx} 轮：没等到广告结束（连续 {idle_count}/{MAX_IDLE_ROUNDS} 轮没广告了）")
            if idle_count >= MAX_IDLE_ROUNDS:
                log(f"  连着 {MAX_IDLE_ROUNDS} 轮都没领到，今天可能领满了，自动停下")
                break
            time.sleep(3)
            continue

        # 点两下领奖，然后自动进下一轮
        claim_res = claim_reward()
        if claim_res == 1:
            success_count += 1
            idle_count = 0
            log(f"  ✅ 第 {round_idx} 轮领到啦！一共领了 {success_count} 次")
        else:
            idle_count += 1
            log(f"  第 {round_idx} 轮没领到（连续 {idle_count}/{MAX_IDLE_ROUNDS} 轮失败）")
            if idle_count >= MAX_IDLE_ROUNDS:
                log(f"  连着 {MAX_IDLE_ROUNDS} 轮都没领到，自动停下")
                break

        # 每轮之间歇一下，别太急
        time.sleep(1)

    return success_count


def main():
    """脚本总入口：按顺序把 5 个步骤跑一遍"""
    log("🎵 opt project 自动领时长小助手，启动！")
    log("   接下来我会：关开屏广告 → 进广告 → 自动领奖，一直循环")
    try:
        # 1. 先量屏幕、认好按钮位置
        init_regions()
        Ocr.set_engine(OCR_ENGINE)
        # 2. 打开 App
        if not launch_app():
            log("❌ App 打不开，脚本停下了。请确认手机上装了这个 App")
            return
        # 3. 跳过开屏广告
        skip_splash_ad(timeout=5)
        # 4. 开始自动领奖循环
        total = run_ad_loop()
        # 5. 收尾，告诉你领了多少次
        log("=" * 60)
        log(f"✅ 结束啦，这次一共帮你领了 {total} 次")
        try:
            notify(f"自动领时长完成，成功 {total} 次")
        except Exception:
            pass
    except Exception as e:
        log(f"❌ 出了点问题：{e}")
        traceback.print_exc()
    finally:
        log("脚本已退出")


# ============== 脚本最底下这行别删，AScript 靠它启动 ==============
main()
