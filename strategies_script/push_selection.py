# -*- coding: utf-8 -*-
"""
push_selection.py —— 读取选股 JSON，通过方糖(Server 酱)推送选股结果到微信

输入: 选股脚本 --output 生成的 selection.json
推送: desp 为 Markdown；换行用空行(\\n\\n)避免方糖把单换行折叠。

用法:
  python push_selection.py --input data/selection.json
"""
import argparse
import json
import os

import requests

KEYS_STR = os.getenv("SERVERCHAN_KEY", "")


def build_content(d: dict) -> str:
    """把选股 JSON 组装成可读推送正文"""
    lines = []
    lines.append(f"📋 选股日期 **{d['as_of']}**（{d['branch']}）")
    lines.append(f"全市场 **{d['raw_count']}** 只 → 过滤后 **{d['valid_count']}** 只")
    lines.append("")
    if d.get("aborted"):
        lines.append("⚠️ 本次调仓放弃：选股池不足，清仓观望")
    else:
        lines.append("**买入清单（次交易日本周开盘，等权各 20%）**")
        for s in d["selected"]:
            name = s.get("name", "") or ""
            lines.append(f"- `{s['code']}` {name}　昨收 **{s['close_lag1']:.2f}**　"
                         f"市值 {s['total_mv'] / 1e8:.2f}亿")
        lines.append("")
        lines.append("> 下周按清单等权买入；持仓若出现 ST 尽快卖出；"
                     "买入量建议不超过当日成交 5%")
    # 方糖 Markdown: 单 \\n 会折叠, 用空行分段保证每行独立
    return "\n\n".join(lines)


def push_to_wechat(title: str, content: str):
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
            print(f"✅ 已推送 ...{key[-4:]}")
        except Exception as e:
            print(f"❌ 推送失败 ({key[-4:]}): {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="推送选股结果到微信")
    parser.add_argument("--input", required=True, help="选股 JSON 路径")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    content = build_content(data)
    title = f"📈 选股清单 {data['as_of']}（小市值低价 top5）"
    print("--- 推送预览 ---")
    print(content)
    print("----------------")
    push_to_wechat(title, content)