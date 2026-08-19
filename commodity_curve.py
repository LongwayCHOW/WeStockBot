# -*- coding: utf-8 -*-
"""
commodity_curve.py — 大宗商品 900 个交易日走势图（国内外对照）推送机器人

数据源：新浪期货历史 K 线接口
  - 国内主力连续合约: InnerFuturesNewService.getDailyKLine?symbol=RB0
    (历史自 2009 年起, 远超 900 交易日)
  - 海外品种: GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=GC
    (历史自 2016 年起, 黄金/白银/铜/原油/燃油/大豆/玉米/白糖/棉花等充足)

流程（两阶段, 由 workflow 编排）:
  1. --render-only: 抓数据 → matplotlib 绘制国内外双轴对比图 → 保存到 charts/
  2. --push-only:   遍历 charts/ 图片 → 用 raw.githubusercontent.com 外链 → 方糖推送

图片托管方案: 图片 commit 进仓库 charts/ 目录并 push,
  推送时通过 https://raw.githubusercontent.com/<owner>/<repo>/main/charts/<file>.png 引用,
  这是 GitHub Actions 上唯一稳定可靠的"图床"(telegra.ph/catbox/0x0.st 均实测不可用)。
"""
import os
import re
import sys
import json
import shutil
import datetime

import requests
import pandas as pd
from urllib.parse import quote

import matplotlib
matplotlib.use("Agg")  # 无显示环境, 绘制到文件
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ================= 配置区域 =================
# 方糖(Server酱)推送 Key, 与现有脚本一致从环境变量读取
KEYS_STR = os.getenv("SERVERCHAN_KEY", "")

# 观察窗口: 最近 N 个交易日
N_DAYS = 900

# 网站/仓库保留最近 KEEP_DAYS 个日期目录的图片, 防止仓库无限膨胀
# (改这里即可调整: 1=只保留当日, 5=最近5天, 0=全部保留)
KEEP_DAYS = 5

# 国内外对照品种对 (名称带交易所后缀, 明确真实标的)
#   dom_symbol: 国内主力连续合约代码(新浪 InnerFuturesNewService)
#   dom_name:   国内品种名(含交易所)
#   dom_unit:   国内价格单位
#   intl_symbol: 海外品种代码(新浪 GlobalFuturesService)
#   intl_name:  海外品种名(含交易所)
#   intl_unit:  海外价格单位
PAIRS = [
    # ---- 贵金属 & 有色 ----
    {"dom_symbol": "AU0", "dom_name": "沪金[上期所]",   "dom_unit": "元/克",     "intl_symbol": "GC",  "intl_name": "纽约金[COMEX]",   "intl_unit": "美元/盎司"},
    {"dom_symbol": "AG0", "dom_name": "沪银[上期所]",   "dom_unit": "元/千克",   "intl_symbol": "SI",  "intl_name": "纽约银[COMEX]",   "intl_unit": "美元/盎司"},
    {"dom_symbol": "CU0", "dom_name": "沪铜[上期所]",   "dom_unit": "元/吨",     "intl_symbol": "HG",  "intl_name": "美铜[COMEX]",    "intl_unit": "美元/磅"},
    # ---- 能源 ----
    {"dom_symbol": "SC0", "dom_name": "原油SC[上期能源]", "dom_unit": "元/桶",   "intl_symbol": "CL",  "intl_name": "WTI原油[NYMEX]", "intl_unit": "美元/桶"},
    {"dom_symbol": "FU0", "dom_name": "燃料油[上期所]", "dom_unit": "元/吨",   "intl_symbol": "HO",  "intl_name": "取暖油[NYMEX]",   "intl_unit": "美元/加仑"},
    # ---- 油脂油料 (M0 原误对应到大豆S, 修正为 CBOT 豆粕 SM; 豆一 A0 才对应对大S) ----
    {"dom_symbol": "M0",  "dom_name": "豆粕[大商所]",  "dom_unit": "元/吨",    "intl_symbol": "SM",  "intl_name": "豆粕[CBOT]",      "intl_unit": "美分/蒲式耳"},
    {"dom_symbol": "Y0",  "dom_name": "豆油[大商所]",  "dom_unit": "元/吨",    "intl_symbol": "BO",  "intl_name": "豆油[CBOT]",      "intl_unit": "美分/磅"},
    {"dom_symbol": "A0",  "dom_name": "豆一[大商所]",  "dom_unit": "元/吨",    "intl_symbol": "S",   "intl_name": "大豆[CBOT]",      "intl_unit": "美分/蒲式耳"},
    # ---- 农产品 ----
    {"dom_symbol": "C0",  "dom_name": "玉米[大商所]",  "dom_unit": "元/吨",    "intl_symbol": "C",   "intl_name": "玉米[CBOT]",      "intl_unit": "美分/蒲式耳"},
    {"dom_symbol": "SR0", "dom_name": "白糖[郑商所]",  "dom_unit": "元/吨",    "intl_symbol": "SB",   "intl_name": "11号糖[ICE]",     "intl_unit": "美分/磅"},
    {"dom_symbol": "CF0", "dom_name": "棉花[郑商所]",  "dom_unit": "元/吨",    "intl_symbol": "CT",   "intl_name": "棉花[ICE]",       "intl_unit": "美分/磅"},
]

# 盘前宏观指数(合并自 original main.py): 美股/港股指数 + 汇率
# 新浪实时 hq.sinajs.cn 代码 → 展示名; 期货配对见下方 FUTURE_GROUPS
MACRO_SYMBOLS = [
    {"code": "gb_ixic",    "name": "纳指",      "type": "us"},
    {"code": "gb_inx",     "name": "标普500",   "type": "us"},
    {"code": "rt_hkHSI",   "name": "恒指",      "type": "hk"},
    {"code": "fx_susdcny", "name": "美元/人民币", "type": "fx"},
]

# 盘前期货配对(方案B): 按品种分组, 每组分"海外(hf_, 隔夜动向)+国内(nf_, 昨收)"相邻行方便对比
#   字段: (分类, 品种, 海外hf代码或无, 海外名, 国内nf代码或无, 国内名)
FUTURE_GROUPS = [
    # ---- 贵金属 & 有色 ----
    ("贵金属", "黄金",   "hf_GC", "COMEX黄金",     "nf_AU0", "沪金[上期所]"),
    ("贵金属", "白银",   "hf_SI", "COMEX白银",     "nf_AG0", "沪银[上期所]"),
    ("贵金属", "铜",     "hf_HG", "COMEX美铜",     "nf_CU0", "沪铜[上期所]"),
    # ---- 能源 ----
    ("能源",   "原油",   "hf_CL", "NYMEX原油",     "nf_SC0", "原油[上期能源]"),
    ("能源",   "燃料油", "hf_HO", "取暖油[NYMEX]",  "nf_FU0", "燃料油[上期所]"),
    ("能源",   "布伦特", "hf_OIL", "ICE布伦特",     None,      None),
    ("能源",   "天然气", "hf_NG", "NYMEX天然气",   None,      None),
    # ---- 油脂油料 ----
    ("油脂油料", "大豆",  "hf_S",  "CBOT大豆",     "nf_A0", "豆一[大商所]"),
    ("油脂油料", "豆粕",  "hf_SM", "CBOT豆粕",     "nf_M0", "豆粕[大商所]"),
    ("油脂油料", "豆油",  "hf_BO", "CBOT豆油",     "nf_Y0", "豆油[大商所]"),
    # ---- 农产品 ----
    ("农产品", "玉米",    "hf_C",  "CBOT玉米",     "nf_C0", "玉米[大商所]"),
    ("农产品", "小麦",    "hf_W",  "CBOT小麦",     None,      None),
    ("农产品", "棉花",    "hf_CT", "ICE棉花",      "nf_CF0", "棉花[郑商所]"),
    ("农产品", "白糖",    "hf_SB", "ICE11号糖",    "nf_SR0", "白糖[郑商所]"),
]

# 图片保存目录: charts/YYYY-MM-DD/ 按日期分子目录
CHARTS_DIR = "charts"
# 图片走 jsdelivr CDN 加速 (raw.githubusercontent 国内访问不稳)
JS_URL_PREFIX = "https://cdn.jsdelivr.net/gh/LongwayCHOW/WeStockBot@main/charts"
# GitHub Pages 画廊入口 (用户微信里打开看全部图片)
PAGES_URL = "https://longwaychow.github.io/WeStockBot/"

# ================= 数据抓取 =================

def fetch_ohlc(url):
    """
    请求新浪期货历史 K 线接口(jsonp), 解析出 [date, close] 序列。

    国内接口字段: {"d":日期, "o":开, "h":高, "l":低, "c":收, "v":量}
    海外接口字段: {"date":日期, "open":开, "high":高, "low":低, "close":收}
    """
    resp = requests.get(url, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    })
    text = resp.text

    # 提取 jsonp 包裹的数组: var t=([ {...}, ... ])
    m = re.search(r"\(\s*(\[.*\])\s*\)\s*;?\s*$", text, re.S)
    if not m:
        return None
    rows = json.loads(m.group(1))
    if not rows:
        return None

    # 兼容国内(d/o/h/l/c)与海外(date/open/close)两种字段名
    records = []
    for r in rows:
        date = r.get("d") or r.get("date")
        close = r.get("c") or r.get("close")
        if not date or close is None:
            continue
        try:
            records.append((pd.Timestamp(date), float(close)))
        except Exception:
            continue

    df = pd.DataFrame(records, columns=["date", "close"]).drop_duplicates(subset="date")
    df = df.set_index("date")["close"].sort_index()
    return df

def fetch_domestic(symbol):
    """抓取国内主力连续合约日 K"""
    url = (f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
           f"var%20t=/InnerFuturesNewService.getDailyKLine?symbol={symbol}")
    return fetch_ohlc(url)

def fetch_intl(symbol):
    """抓取海外品种日 K"""
    url = (f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
           f"var%20t=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={symbol}")
    return fetch_ohlc(url)


def fetch_macro():
    """
    抓取盘前宏观行情(合并自原 main.py 盘前推送): 美股/港股指数 + 美元汇率。
    数据源: 新浪实时行情 hq.sinajs.cn; 返回多行文本用于推送。
    """
    codes = [m["code"] for m in MACRO_SYMBOLS]
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    try:
        resp = requests.get(url, timeout=15, headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        })
        text = resp.text
    except Exception as e:
        return f"⚠️ 宏观数据获取失败: {e}"

    lines = []
    for m in MACRO_SYMBOLS:
        match = re.search(rf'var hq_str_{m["code"]}="(.*?)";', text)
        if not match:
            lines.append(f"⚪ **{m['name']}**: 无数据")
            continue
        parts = match.group(1).split(',')
        try:
            if m["type"] == "us":
                price, change_pct = float(parts[1]), float(parts[2])
                fmt = f"{price:,.2f} ({change_pct:+.2f}%)"
            elif m["type"] == "hk":
                price, change_pct = float(parts[6]), float(parts[8])
                fmt = f"{price:,.2f} ({change_pct:+.2f}%)"
            else:  # fx 汇率: 只显示价格
                price = float(parts[1])
                change_pct = 0.0
                fmt = f"{price:.4f}"
            icon = "🔴" if change_pct > 0 else ("🟢" if change_pct < 0 else "⚪")
            lines.append(f"{icon} **{m['name']}**: {fmt}")
        except Exception:
            lines.append(f"⚪ **{m['name']}**: 解析出错")
    return "\n".join(lines)


def fetch_futures():
    """
    抓取盘前期货配对行情(方案B)。
    按 FUTURE_GROUPS 分组: 海外(hf_)显示隔夜涨跌幅, 国内(nf_)盘前未开盘显示昨收价;
    同一品种海外/国内相邻两行, 方便对比。
    """
    # 批量请求所有海外+国内代码
    codes = []
    for _cat, _nm, hf, _hnm, nf, _dnm in FUTURE_GROUPS:
        if hf:
            codes.append(hf)
        if nf:
            codes.append(nf)
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    try:
        resp = requests.get(url, timeout=15, headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        })
        text = resp.text
    except Exception as e:
        return f"⚠️ 期货数据获取失败: {e}"

    # 解析: data[sym] = (价格, 昨结/昨收)
    data = {}
    for sym in codes:
        match = re.search(rf'var hq_str_{sym}="(.*?)";', text)
        if not match:
            continue
        parts = match.group(1).split(',')
        try:
            if sym.startswith("hf_"):
                # 海外期货: parts[0]=现价, parts[7]=昨结
                price = float(parts[0])
                prev = float(parts[7]) if parts[7] else price
            else:
                # 国内期货(nf_): parts[2]=最新价(盘前即昨收)
                price = float(parts[2])
                prev = price  # 昨收价无当日涨跌幅
            data[sym] = (price, prev)
        except Exception:
            continue

    lines = []
    cur_cat = None
    for cat, _nm, hf, hname, nf, dname in FUTURE_GROUPS:
        if cat != cur_cat:
            lines.append(f"\n**{cat}**")
            cur_cat = cat

        # 海外行(隔夜动向)
        if hf and hf in data:
            price, prev = data[hf]
            pct = ((price - prev) / prev * 100) if prev else 0.0
            icon = "🔴" if pct > 0 else ("🟢" if pct < 0 else "⚪")
            lines.append(f"{icon} {hname}: {price:,.2f} ({pct:+.2f}%)")
        # 国内行(昨收, 紧跟海外行方便对比)
        if nf and nf in data:
            price, _ = data[nf]
            lines.append(f"     {dname}: {price:,.2f}（昨收）")
    return "\n".join(lines)


# ================= 绘图 =================

def setup_chinese_font():
    """
    配置 matplotlib 中文字体, 防止图内中文显示为方框。

    背景: Ubuntu 的 fonts-noto-cjk 是 ttc 容器(含 SC/TC/JP/KR 多语言 face),
    matplotlib 通常只注册到第一个 face 的名字(往往是 "Noto Sans CJK JP" 或
    "Noto Sans CJK SC" 之一, 不同版本不一样), 因此精确名字匹配不可靠。
    修复策略: 先试名字匹配(含多种变体), 失败则直接按字体文件路径注册。
    """
    # 1) 名字匹配(覆盖 SC/JP/TC 变体, 因为 ttc 首 face 可能是任意一个)
    candidates = ["Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK TC",
                  "WenQuanYi Zen Hei", "SimHei", "Microsoft YaHei"]
    for name in candidates:
        if any(name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return True

    # 2) 名字匹配失败 → 直接按文件路径注册 Ubuntu 的 Noto CJK (apt 安装位置)
    for fp in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]:
        if os.path.exists(fp):
            try:
                fm.fontManager.addfont(fp)
                face_name = fm.FontProperties(fname=fp).get_name()
                plt.rcParams["font.sans-serif"] = [face_name]
                plt.rcParams["axes.unicode_minus"] = False
                print(f"✅ 中文字体已注册: {face_name} ({fp})")
                return True
            except Exception as e:
                print(f"⚠️ 字体注册失败 {fp}: {e}")

    print("⚠️ 未找到中文字体, 图中中文将显示为方框")
    return False

def render_pair(pair, dom_s, intl_s):
    """
    绘制单个品种对的国内外双轴对比图, 保存为 PNG。
    双轴: 左轴(蓝)=国内价格, 右轴(红)=海外价格, 便于直观对照两边走势与差价。
    返回 (图片文件名, 图表标题, 国内最新统计, 海外最新统计); 失败返回 None。
    """
    name = f"{pair['dom_name']} / {pair['intl_name']}"

    # ---- 对齐: 各自取最近 N_DAYS 个交易日, 再按日期取交集 ----
    dom = dom_s.tail(N_DAYS).rename("dom")
    intl = intl_s.tail(N_DAYS).rename("intl")
    df = pd.concat([dom, intl], axis=1).dropna()
    if len(df) < 30:
        print(f"⚠️ {name}: 对齐后数据不足 ({len(df)} 条), 跳过")
        return None

    days = len(df)
    dom_close = df["dom"]
    intl_close = df["intl"]

    # ---- 绘制双轴图 ----
    # 宽度 11 英寸时实际输出仅约 1095px(tight裁剪), 900 个交易日挤在一起难看清近期起伏。
    # 改为 22 英寸宽(输出约 2200px, 翻倍), 高度适度增至 7 防止 4:1 过扁。
    fig, ax1 = plt.subplots(figsize=(22, 7))
    ax2 = ax1.twinx()

    line1, = ax1.plot(dom_close.index, dom_close.values, color="#1f77b4", linewidth=1.4, label=f"{pair['dom_name']}")
    line2, = ax2.plot(intl_close.index, intl_close.values, color="#d62728", linewidth=1.4, label=f"{pair['intl_name']}")

    ax1.set_xlabel("日期")
    ax1.set_ylabel(pair["dom_name"] + " 价格 (" + pair["dom_unit"] + ")", color="#1f77b4")
    ax2.set_ylabel(pair["intl_name"] + " 价格 (" + pair["intl_unit"] + ")", color="#d62728")
    ax1.grid(True, alpha=0.3)

    # 最新价 + 窗口内涨跌幅标注
    dom_last, dom_first = float(dom_close.iloc[-1]), float(dom_close.iloc[0])
    intl_last, intl_first = float(intl_close.iloc[-1]), float(intl_close.iloc[0])
    dom_pct = (dom_last / dom_first - 1) * 100
    intl_pct = (intl_last / intl_first - 1) * 100

    ax1.annotate(f"{dom_last:,.2f} ({dom_pct:+.1f}%)", xy=(dom_close.index[-1], dom_last),
                 color="#1f77b4", fontsize=10, ha="right", va="bottom")
    ax2.annotate(f"{intl_last:,.2f} ({intl_pct:+.1f}%)", xy=(intl_close.index[-1], intl_last),
                 color="#d62728", fontsize=10, ha="right", va="top")

    ax1.legend(handles=[line1, line2], loc="upper left", fontsize=10)
    plt.title(f"{name} — 近 {days} 个交易日走势对照", fontsize=13)
    fig.autofmt_xdate()

    # 保存: 按日期分子目录, 文件名带品种中文名, 便于用户识别是哪个期货
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    subdir = os.path.join(CHARTS_DIR, today)
    os.makedirs(subdir, exist_ok=True)
    fname = f"{pair['dom_name']}-{pair['intl_name']}_{pair['dom_symbol']}-{pair['intl_symbol']}.png"
    path = os.path.join(subdir, fname)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)

    latest = df.index[-1].strftime("%Y-%m-%d")
    dom_stat = (pair["dom_name"], dom_last, pair["dom_unit"], dom_pct)
    intl_stat = (pair["intl_name"], intl_last, pair["intl_unit"], intl_pct)
    print(f"✅ {name}: {days} 天 | {latest} 国内 {dom_last:,.2f} ({dom_pct:+.1f}%) | 海外 {intl_last:,.2f} ({intl_pct:+.1f}%)")
    return fname, f"**{name}** ({latest}, {days}个交易日)", dom_stat, intl_stat

# ================= 阶段1: 渲染 =================

def generate_index_html():
    """
    生成画廊索引页 index.html (GitHub Pages 入口)。
    页面展示最新日期目录下的全部图片, 图片走 jsdelivr CDN 加速。
    用户微信里打开 Pages 链接即可浏览全部品种对照图。
    """
    date_dirs = [d for d in os.listdir(CHARTS_DIR)
                 if os.path.isdir(os.path.join(CHARTS_DIR, d)) and d[0].isdigit()]
    if not date_dirs:
        print("⚠️ 无日期目录, 跳过画廊页生成")
        return False
    latest = sorted(date_dirs)[-1]
    latest_dir = os.path.join(CHARTS_DIR, latest)
    pngs = sorted(f for f in os.listdir(latest_dir) if f.endswith(".png"))
    if not pngs:
        print("⚠️ 最新日期目录无图片")
        return False

    # 每张图一个条目: 品种名(从文件名提取) + 图片(jsdelivr CDN 加速)
    items = []
    for f in pngs:
        base = f[:-4]
        pair_name = base.split("_")[0].replace("-", " vs ")  # "沪金-纽约金" → "沪金 vs 纽约金"
        img_url = f"{JS_URL_PREFIX}/{latest}/{quote(f)}"
        items.append(f'<h3>{pair_name}</h3>'
                     f'<img src="{img_url}" alt="{pair_name}" '
                     f'style="width:100%;height:auto;margin-bottom:8px;"/>')

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日期货 ({latest})</title>
</head>
<body style="font-family:sans-serif;max-width:720px;margin:0 auto;padding:12px;background:#f7f7f7;">
<h2 style="text-align:center;">📈 每日期货 — {latest}</h2>
<p style="text-align:center;color:#888;">大宗商品国内外对照 · 近 900 个交易日</p>
{''.join(items)}
</body>
</html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 画廊页已生成: index.html ({len(pngs)} 张图)")
    return True


def cleanup_old_charts():
    """
    清理过期图片: 保留最近 KEEP_DAYS 个日期目录, 删除更早的目录。
    防止 charts/ 无限膨胀拖大仓库; 画廊页永远只展示最新日期, 所以旧目录删除无影响。
    """
    if KEEP_DAYS <= 0:
        return  # 0 或负数 = 全部保留
    date_dirs = [d for d in os.listdir(CHARTS_DIR)
                 if os.path.isdir(os.path.join(CHARTS_DIR, d)) and d[0].isdigit()]
    date_dirs.sort()
    if len(date_dirs) <= KEEP_DAYS:
        return
    for d in date_dirs[:-KEEP_DAYS]:
        shutil.rmtree(os.path.join(CHARTS_DIR, d))
        print(f"🗑️ 已清理过期目录: charts/{d}")


def render_all():
    """抓取全部品种数据并绘制图片, 返回 [(fname, title, dom_stat, intl_stat), ...]"""
    os.makedirs(CHARTS_DIR, exist_ok=True)
    cleanup_old_charts()  # 先清理过期目录, 再生成当天图片
    results = []
    for pair in PAIRS:
        try:
            dom_s = fetch_domestic(pair["dom_symbol"])
            intl_s = fetch_intl(pair["intl_symbol"])
            if dom_s is None or intl_s is None or len(dom_s) == 0 or len(intl_s) == 0:
                print(f"⚠️ {pair['dom_name']}/{pair['intl_name']}: 接口无数据, 跳过")
                continue
            r = render_pair(pair, dom_s, intl_s)
            if r:
                results.append(r)
        except Exception as e:
            print(f"❌ {pair['dom_name']}/{pair['intl_name']}: {e}")
    generate_index_html()
    return results

# ================= 阶段2: 推送 =================

def push_to_wechat(title, content):
    """方糖(Server酱)推送, 支持多 Key 逗号分隔(与现有脚本一致)"""
    if not KEYS_STR:
        print("⚠️ 未配置 SERVERCHAN_KEY")
        return
    for key in KEYS_STR.split(","):
        key = key.strip()
        if not key:
            continue
        try:
            requests.post(f"https://sctapi.ftqq.com/{key}.send",
                          data={"title": title, "desp": content}, timeout=20)
            print(f"✅ 已推送给 ...{key[-4:]}")
        except Exception as e:
            print(f"❌ 推送失败 ({key[-4:]}): {e}")

def push_all():
    """
    推送 GitHub Pages 画廊链接。
    背景: 方糖/微信不渲染推送消息中的外链图片, 因此改为推送"打开画廊页"链接,
    用户微信里点开 GitHub Pages 即可浏览全部图片(图片经 jsdelivr CDN 加速)。
    """
    if not os.path.isdir(CHARTS_DIR):
        print("❌ charts/ 目录不存在, 请先运行 --render-only 生成图片")
        return

    date_dirs = [d for d in os.listdir(CHARTS_DIR)
                 if os.path.isdir(os.path.join(CHARTS_DIR, d)) and d[0].isdigit()]
    if not date_dirs:
        print("❌ charts/ 无日期目录")
        return
    latest = sorted(date_dirs)[-1]
    latest_dir = os.path.join(CHARTS_DIR, latest)
    pngs = sorted(f for f in os.listdir(latest_dir) if f.endswith(".png"))
    if not pngs:
        print("❌ 最新日期目录无图片")
        return

    # 品种清单(推送里列出来, 让用户知道有哪些图)
    names = []
    for f in pngs:
        base = f[:-4]
        names.append(base.split("_")[0].replace("-", " vs "))

    if len(names) <= 4:
        name_desc = "：" + "、".join(names)
    elif len(names) <= 10:
        name_desc = f"（{len(names)} 个品种：" + "、".join(names[:5]) + " 等）"
    else:
        name_desc = f"（{len(names)} 个品种）"

    # GitHub 文件夹直链(备选, 不依赖 Pages)
    gh_tree_url = "https://github.com/LongwayCHOW/WeStockBot/tree/main/" + os.path.join(CHARTS_DIR, latest)

    # 盘前宏观快照(指数/汇率 + 期货配对), 放在推送最顶部
    macro = fetch_macro() + "\n\n" + fetch_futures()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"**🌍 盘前宏观**\n{macro}\n\n"
        f"**📈 期货走势**：共 **{len(pngs)}** 张国内外对照图{name_desc}\n\n"
        f"👉 [点击打开每日期货画廊]({PAGES_URL})\n\n"
        f"> 微信内直接打开即可查看; 图片已用 jsdelivr CDN 加速;"
        f" 备选: [GitHub 文件夹]({gh_tree_url})"
    )
    title = f"🌍盘前 📈每日期货 {latest}"
    print("--- 预览 ---")
    print(content)
    print("-----------")
    push_to_wechat(title, content)

# ================= 入口 =================

if __name__ == "__main__":
    setup_chinese_font()
    mode = sys.argv[1] if len(sys.argv) > 1 else "--render-only"
    if mode == "--render-only":
        render_all()
    elif mode == "--push-only":
        push_all()
    else:
        print("用法: python commodity_curve.py [--render-only | --push-only]")