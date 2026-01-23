import akshare as ak
import pandas as pd
import datetime
import requests
import os
import re

# ================= 配置区域 =================
KEYS_STR = os.getenv("SERVERCHAN_KEY", "")

# 股票池与估值规则配置
# code: 股票代码 (A股直接写数字，港股加前缀 hk 或不加由逻辑判断，建议港股用 5位数字)
# name: 名称
# type: 'A' 或 'H'
# rules: 列表，包含多个维度。
#   - metric: 'pe_ttm' (市盈率TTM), 'pb' (市净率), 'dv_ratio' (股息率%)
#   - buy: 买入阈值 (击球区)
#   - sell: 卖出阈值 (出售区)
#   - reverse: False (越小越好，如PE/PB), True (越大越好，如股息率)

TARGETS = [
    # =========================================
    # 👑 皇冠明珠 (核心资产，定价权)
    # =========================================
    {
        "code": "600519", "name": "贵州茅台", "type": "A",
        "rules": [
            # 股息率只有单向大小，buy=3.5 代表大于3.5是买点，sell设为 None 或一个极低值仅作参考
            # 这里我们特殊处理：股息率不计算分位，只显示数值
            {"metric": "pe_ttm", "buy": 25, "sell": 40, "reverse": False, "desc": "PE(极佳<20)"},
            {"metric": "dv_ratio", "buy": 3.5, "sell": 1.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "000858", "name": "五粮液", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 16, "sell": 30, "reverse": False, "desc": "PE(极佳<13)"},
            {"metric": "dv_ratio", "buy": 4.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "000333", "name": "美的集团", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 15, "sell": 22, "reverse": False, "desc": "PE(极佳<12)"},
            {"metric": "dv_ratio", "buy": 5.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "600436", "name": "片仔癀", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 35, "sell": 65, "reverse": False, "desc": "PE(极佳<30)"},
            {"metric": "dv_ratio", "buy": 2.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "600329", "name": "达仁堂", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 12, "sell": 28, "reverse": False, "desc": "PE(极佳<10)"},
            {"metric": "dv_ratio", "buy": 3.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "300760", "name": "迈瑞医疗", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 22, "sell": 42, "reverse": False, "desc": "PE(极佳<18)"},
            {"metric": "dv_ratio", "buy": 1.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "600660", "name": "福耀玻璃", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 16, "sell": 28, "reverse": False, "desc": "PE(极佳<13)"},
            {"metric": "dv_ratio", "buy": 2.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "02328", "name": "中国财险(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.7, "sell": 1.2, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 6.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00700", "name": "腾讯控股(H)", "type": "H",
        "rules": [
            # 注: AkShare 返回的是标准 PE，非 Non-IFRS，需自行留意差异
            {"metric": "pe_ttm", "buy": 18, "sell": 30, "reverse": False, "desc": "PE"}
        ]
    },
    {
        "code": "600900", "name": "长江电力", "type": "A",
        "rules": [
            # 股息率: >3.8买, <2.6卖
            {"metric": "dv_ratio", "buy": 3.8, "sell": 2.6, "reverse": True, "desc": "股息率"}
            # CSV 中提到股价 < 25，这里暂只监控股息率，可人工辅助看价格
        ]
    },

    # =========================================
    # 💰 现金奶牛 (高股息，低估值)
    # =========================================
    {
        "code": "00883", "name": "中国海油(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 7, "sell": None, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 7.0, "sell": 5.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "03988", "name": "中国银行(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.4, "sell": 0.65, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 8.0, "sell": 5.0, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00939", "name": "建设银行(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.48, "sell": 0.70, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 7.0, "sell": 4.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00941", "name": "中国移动(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 11, "sell": None, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 6.5, "sell": 4.5, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "00874", "name": "白云山(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 10, "sell": 15, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 4.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "000651", "name": "格力电器", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 8, "sell": 12, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 7.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "603288", "name": "海天味业", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 22, "sell": 42, "reverse": False, "desc": "PE(极佳<18)"}
        ]
    },
    {
        "code": "002027", "name": "分众传媒", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 14, "sell": 23, "reverse": False, "desc": "PE(极佳<11)"}
        ]
    },

    # =========================================
    # 🦁 周期猎物 (底部埋伏，顶部逃顶)
    # =========================================
    {
        "code": "01919", "name": "中远海控(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.7, "sell": 1.3, "reverse": False, "desc": "PB(运价底部)"},
            {"metric": "dv_ratio", "buy": 8.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "601668", "name": "中国建筑", "type": "A",
        "rules": [
            {"metric": "pb", "buy": 0.55, "sell": 0.8, "reverse": False, "desc": "PB"},
            {"metric": "pe_ttm", "buy": 5, "sell": None, "reverse": False, "desc": "PE"}
        ]
    },
    {
        "code": "01099", "name": "国药控股(H)", "type": "H",
        "rules": [
            {"metric": "pe_ttm", "buy": 8, "sell": 14, "reverse": False, "desc": "PE"},
            {"metric": "dv_ratio", "buy": 5.5, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "06030", "name": "中信证券(H)", "type": "H",
        "rules": [
            {"metric": "pb", "buy": 0.9, "sell": 1.7, "reverse": False, "desc": "PB(牛熊周期)"}
        ]
    },
    {
        "code": "600019", "name": "宝钢股份", "type": "A",
        "rules": [
            {"metric": "pb", "buy": 0.55, "sell": 0.9, "reverse": False, "desc": "PB"},
            {"metric": "dv_ratio", "buy": 6.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    },
    {
        "code": "002714", "name": "牧原股份", "type": "A",
        "rules": [
            # 注: 周期股亏损时 PE 无意义或为负。这里配置仅作参考。
            # CSV: PE < 10 (全行业巨亏), PE > 25 (暴利)
            {"metric": "pe_ttm", "buy": 10, "sell": 25, "reverse": False, "desc": "PE(需结合周期)"}
        ]
    },
    {
        "code": "601088", "name": "中国神华", "type": "A",
        "rules": [
            # CSV 规则提到 H 股 PE < 8，这里监控 A 股股息和 PE
            {"metric": "dv_ratio", "buy": 8.0, "sell": None, "reverse": True, "desc": "股息率"},
            {"metric": "pe_ttm", "buy": None, "sell": 12, "reverse": False, "desc": "PE(卖出)"}
        ]
    },
    {
        "code": "601899", "name": "紫金矿业", "type": "A",
        "rules": [
            {"metric": "pe_ttm", "buy": 15, "sell": 30, "reverse": False, "desc": "PE"},
            {"metric": "pb", "buy": None, "sell": 5.5, "reverse": False, "desc": "PB(卖出)"},
            {"metric": "dv_ratio", "buy": 5.0, "sell": None, "reverse": True, "desc": "股息率"}
        ]
    }
]

def get_realtime_data(targets):
    """
    批量获取 A 股和港股的实时估值数据
    返回字典: {'600519': {'pe_ttm': 20.5, 'pb': 5.1, 'dv_ratio': 2.8, 'price': 1500}, ...}
    """
    data_map = {}
    
    # 1. 分离 A 股和 H 股代码
    a_codes = [t['code'] for t in targets if t['type'] == 'A']
    h_codes = [t['code'] for t in targets if t['type'] == 'H']
    
    # 2. 抓取 A 股数据 (ak.stock_zh_a_spot_em)
    if a_codes:
        print("📡 正在拉取 A 股实时数据...")
        try:
            df_a = ak.stock_zh_a_spot_em()
            # 过滤出我们关注的股票
            df_a = df_a[df_a['代码'].isin(a_codes)]
            for _, row in df_a.iterrows():
                code = row['代码']
                data_map[code] = {
                    'price': row['最新价'],
                    'pe_ttm': row['市盈率-动态'], # 注意：东方财富接口返回的是动态市盈率，近似 TTM
                    'pb': row['市净率'],
                    'dv_ratio': row['股息率'] # 单位 %
                }
        except Exception as e:
            print(f"⚠️ A 股数据拉取失败: {e}")

    # 3. 抓取 H 股数据 (ak.stock_hk_spot_em)
    if h_codes:
        print("📡 正在拉取 港股 实时数据...")
        try:
            df_h = ak.stock_hk_spot_em()
            # 港股代码 akshare 返回的是 5位 (如 '00700')
            df_h = df_h[df_h['代码'].isin(h_codes)]
            for _, row in df_h.iterrows():
                code = row['代码']
                data_map[code] = {
                    'price': row['最新价'],
                    'pe_ttm': 0, # 港股接口可能不直接返回 PE/PB，需注意
                    'pb': 0,
                    'dv_ratio': 0
                }
                # 尝试从列名中找 PE/PB (AkShare 港股接口列名可能有变)
                # 常见列名: '市盈率(动)', '市净率', '股息率'
                if '市盈率(动)' in row: data_map[code]['pe_ttm'] = row['市盈率(动)']
                if '市净率' in row: data_map[code]['pb'] = row['市净率']
                if '股息率' in row: data_map[code]['dv_ratio'] = row['股息率']
                
        except Exception as e:
            print(f"⚠️ 港股数据拉取失败: {e}")
            
    return data_map

def calculate_percentile(current, buy, sell, reverse=False):
    """
    计算分位值 (0% = 买入点, 100% = 卖出点)
    """
    if current is None or buy is None or sell is None:
        return None
    
    try:
        current = float(current)
        buy = float(buy)
        sell = float(sell)
        
        if reverse:
            # 反向指标 (如股息率)：越大越好
            # 0% 分位对应 Buy (高股息), 100% 分位对应 Sell (低股息)
            if buy == sell: return 0
            pct = (buy - current) / (buy - sell) * 100
        else:
            # 正向指标 (如PE)：越小越好
            # 0% 分位对应 Buy (低PE), 100% 分位对应 Sell (高PE)
            if sell == buy: return 0
            pct = (current - buy) / (sell - buy) * 100
            
        return pct
    except:
        return None

def generate_report():
    data_map = get_realtime_data(TARGETS)
    lines = []
    
    for item in TARGETS:
        code = item['code']
        name = item['name']
        real_data = data_map.get(code)
        
        if not real_data:
            lines.append(f"⚪ **{name}**: 数据缺失")
            continue
            
        item_lines = [f"**{name}** (¥{real_data['price']})"]
        
        for rule in item['rules']:
            metric_key = rule['metric']
            desc = rule['desc']
            buy = rule['buy']
            sell = rule['sell']
            reverse = rule['reverse']
            
            current_val = real_data.get(metric_key)
            
            # 格式化当前值
            val_str = f"{current_val}"
            if metric_key == 'dv_ratio': val_str += "%"
            
            # 情况 1: 完整区间 -> 计算分位
            if buy is not None and sell is not None:
                pct = calculate_percentile(current_val, buy, sell, reverse)
                if pct is not None:
                    # 判断状态图标
                    if pct < 0: icon = "🔥" # 极度低估 (击球区)
                    elif pct < 20: icon = "✅" # 低估
                    elif pct > 100: icon = "⚠️" # 高估
                    elif pct > 80: icon = "🔴" # 风险
                    else: icon = "⚖️" # 合理
                    
                    range_str = f"{buy}-{sell}"
                    item_lines.append(f"• {icon} {desc}: {range_str} | 当前 **{pct:.0f}%** 分位 ({val_str})")
                else:
                    item_lines.append(f"• ⚪ {desc}: 计算出错 ({val_str})")
                continue

            # 情况 2: 只有买入阈值 (缺卖出)
            if buy is not None and sell is None:
                # 判断是否满足买入
                # Reverse(股息): 越大越好 -> Current >= Buy
                # Normal(PE): 越小越好 -> Current <= Buy
                try:
                    is_buy = (reverse and float(current_val) >= float(buy)) or \
                             (not reverse and float(current_val) <= float(buy))
                except:
                    is_buy = False
                    
                icon = "✅" if is_buy else "🔸"
                op = ">" if reverse else "<"
                item_lines.append(f"• {icon} {desc}: {op}{buy} | 当前 {val_str}")
                continue

            # 情况 3: 只有卖出阈值 (缺买入)
            if sell is not None and buy is None:
                # 判断是否满足卖出
                # Reverse(股息): 越大越好 -> Current <= Sell (股息太低，卖出)
                # Normal(PE): 越小越好 -> Current >= Sell (PE太高，卖出)
                try:
                    is_sell = (reverse and float(current_val) <= float(sell)) or \
                              (not reverse and float(current_val) >= float(sell))
                except:
                    is_sell = False
                    
                icon = "⚠️" if is_sell else "⚖️"
                op = "<" if reverse else ">"
                item_lines.append(f"• {icon} {desc}: {op}{sell} | 当前 {val_str}")
                continue

            # 情况 4: 兜底 (不应该出现)
            item_lines.append(f"• ⚪ {desc}: 规则不完整 ({val_str})")
        
        lines.append("\n".join(item_lines))
        lines.append("") # 空行分隔
        
    title = "午间估值雷达: " + datetime.datetime.now().strftime("%H:%M")
    content = "\n".join(lines)
    return title, content

def push_to_wechat(title, content):
    if not KEYS_STR: 
        print("⚠️ 未配置 Key")
        return
    keys = KEYS_STR.split(",")
    for key in keys:
        key = key.strip()
        if not key: continue
        url = f"https://sctapi.ftqq.com/{key}.send"
        requests.post(url, data={"title": title, "desp": content})
        print(f"✅ 推送给 ...{key[-4:]}")

if __name__ == "__main__":
    title, content = generate_report()
    print("----------------")
    print(title)
    print(content)
    print("----------------")
    push_to_wechat(title, content)
