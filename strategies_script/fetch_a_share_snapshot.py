# -*- coding: utf-8 -*-
"""
fetch_a_share_snapshot.py —— 新浪全市场 A 股快照抓取，生成选股行情 CSV

数据源: 新浪 Market_Center.getHQNodeData (node=hs_a，分页遍历全 A 股，含 sh/sz/bj 北交所)
产出 CSV 列: code, name, close_lag1, total_mv
  - close_lag1: 昨收价(settlement)
  - total_mv  : 接口直接返回的总市值(现价口径, 万元)→ 转成元
                (不再折算昨收口径; 市值排序对现价/昨收口径不敏感。)

选股脚本需要但本接口没有的可选列(is_st/is_susp/is_wd/high_limited/listed_date)
不产出，由选股脚本按缺列降级处理(ST 用 name 兜底、科创 688 靠代码判断)。

用法:
  python fetch_a_share_snapshot.py --output data/a_share.csv
"""
import argparse
import csv
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BASE = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData")
PAGE_SIZE = 100   # 新浪接口单页上限约 100
MAX_PAGE = 200    # 安全上限(正常全市场约 56 页)


def fetch_all() -> list[dict]:
    """分页遍历新浪全市场快照, 返回原始 JSON 记录列表(约 5500+ 条)。"""
    rows = []
    page = 1
    while page <= MAX_PAGE:
        params = {"page": page, "num": PAGE_SIZE, "sort": "symbol", "asc": 1, "node": "hs_a"}
        try:
            resp = requests.get(BASE, params=params, timeout=20, headers={
                "Referer": "https://finance.sina.com.cn/", "User-Agent": UA})
            batch = resp.json()
        except Exception as e:
            print(f"[WARN] 第 {page} 页请求失败: {e}，跳过")
            batch = []
        if not batch:
            break  # 无更多数据
        rows.extend(batch)
        page += 1
        time.sleep(0.2)  # 礼貌限速, 避免被限
    return rows


def to_csv(rows: list[dict], out_path: str) -> int:
    """把全市场快照标准化成选股脚本所需 CSV(昨收 + 昨收口径总市值)。"""
    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "close_lag1", "total_mv"])
        for r in rows:
            code = str(r.get("code") or "").strip()
            name = (r.get("name") or "").strip()
            try:
                settle = float(r.get("settlement") or 0)    # 昨收
                mktcap = float(r.get("mktcap") or 0)        # 总市值(万元)
            except Exception:
                continue
            # 昨收或总市值无效则剔除
            if settle <= 0 or mktcap <= 0:
                continue
            # 直接用接口总市值(现价口径), 万元→元
            mv = mktcap * 10000
            w.writerow([code.zfill(6), name, f"{settle:.4f}", f"{mv:.2f}"])
            written += 1
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="新浪全市场A股快照→选股CSV")
    parser.add_argument("--output", required=True, help="CSV 输出路径")
    args = parser.parse_args()

    all_rows = fetch_all()
    n = to_csv(all_rows, args.output)
    print(f"[INFO] 全市场拉到 {len(all_rows)} 只, 标准化写入 {n} 只 → {args.output}")