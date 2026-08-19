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

# 国内外对照品种对
#   dom_symbol: 国内主力连续合约代码(新浪 InnerFuturesNewService)
#   dom_name:   国内品种中文名
#   dom_unit:   国内价格单位
#   intl_symbol: 海外品种代码(新浪 GlobalFuturesService)
#   intl_name:  海外品种中文名
#   intl_unit:  海外价格单位
PAIRS = [
    {"dom_symbol": "AU0", "dom_name": "沪金",   "dom_unit": "元/克",     "intl_symbol": "GC",  "intl_name": "纽约金", "intl_unit": "美元/盎司"},
    {"dom_symbol": "AG0", "dom_name": "沪银",   "dom_unit": "元/千克",   "intl_symbol": "SI",  "intl_name": "纽约银", "intl_unit": "美元/盎司"},
    {"dom_symbol": "CU0", "dom_name": "沪铜",   "dom_unit": "元/吨",     "intl_symbol": "HG",  "intl_name": "美铜",   "intl_unit": "美元/磅"},
    {"dom_symbol": "SC0", "dom_name": "原油",   "dom_unit": "元/桶",     "intl_symbol": "CL",  "intl_name": "纽约原油", "intl_unit": "美元/桶"},
    {"dom_symbol": "FU0", "dom_name": "燃油",   "dom_unit": "元/吨",     "intl_symbol": "HO",  "intl_name": "燃料油", "intl_unit": "美元/加仑"},
    {"dom_symbol": "M0",  "dom_name": "豆粕",   "dom_unit": "元/吨",     "intl_symbol": "S",   "intl_name": "CBOT大豆", "intl_unit": "美分/蒲式耳"},
    {"dom_symbol": "Y0",  "dom_name": "豆油",   "dom_unit": "元/吨",     "intl_symbol": "BO",  "intl_name": "CBOT豆油", "intl_unit": "美分/磅"},
    {"dom_symbol": "C0",  "dom_name": "玉米",   "dom_unit": "元/吨",     "intl_symbol": "C",   "intl_name": "CBOT玉米", "intl_unit": "美分/蒲式耳"},
    {"dom_symbol": "SR0", "dom_name": "白糖",   "dom_unit": "元/吨",     "intl_symbol": "SB",  "intl_name": "NY糖",   "intl_unit": "美分/磅"},
    {"dom_symbol": "CF0", "dom_name": "棉花",   "dom_unit": "元/吨",     "intl_symbol": "CT",  "intl_name": "NY棉花", "intl_unit": "美分/磅"},
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
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
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


def render_all():
    """抓取全部品种数据并绘制图片, 返回 [(fname, title, dom_stat, intl_stat), ...]"""
    os.makedirs(CHARTS_DIR, exist_ok=True)
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

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    content = (
        f"📅 数据更新：**{latest}**（{now}）\n\n"
        f"共 **{len(pngs)}** 张国内外对照图{name_desc}\n\n"
        f"👉 [点击打开每日期货画廊]({PAGES_URL})\n\n"
        f"> 微信内直接打开即可查看; 图片已用 jsdelivr CDN 加速;"
        f" 备选: [GitHub 文件夹]({gh_tree_url})"
    )
    title = f"📈 每日期货 {latest}"
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