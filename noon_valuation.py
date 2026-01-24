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
    [精准版] 批量获取 A 股和港股的实时估值数据
    直接请求东方财富 ulist 接口，只查询目标股票，避免拉取全市场数据导致的超时和缺失。
    """
    data_map = {}
    
    # 1. 构造 secids (东方财富的股票ID)
    # 规则: 
    #   沪A(6开头) -> 1.xxxxxx
    #   深A(0/3开头) -> 0.xxxxxx
    #   港股 -> 116.xxxxx
    secids = []
    
    # 建立映射: secid -> target_code (用于后续匹配回填)
    # 因为接口返回的是 1.600519，我们需要知道它对应 targets 里的 600519
    secid_map = {} 

    print(f"📡 正在精准拉取 {len(targets)} 只目标股票数据...")

    for t in targets:
        code = t['code']
        stype = t['type']
        
        secid = ""
        if stype == 'A':
            # 简单判断沪深
            if str(code).startswith('6'):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"
        elif stype == 'H':
            # 港股通常是 116
            secid = f"116.{code}"
            
        if secid:
            secids.append(secid)
            secid_map[secid] = code

    # 2. 发送请求
    # 字段: f12(代码), f14(名称), f2(最新价), f9(PE-TTM), f23(PB), f133(股息率-港), f115(股息率-A)
    # 注意: A股股息率有时在 f115, 港股在 f133, 我们都请求
    fields = "f12,f14,f2,f9,f23,f133,f115"
    secids_str = ",".join(secids)
    
    # 使用 ulist.np 接口，这是东方财富的"自选股/个股列表"接口，更加稳定
    # ut 参数是必要的 token
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "ut": "f057cbcbce2a86e2866ab8877db1d059",
        "invt": "2",
        "fltt": "2",
        "fields": fields,
        "secids": secids_str
    }
    
    # 伪装浏览器头
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 尝试直连 (为了兼容某些代理环境，也可以尝试去掉 verify=False)
        # requests 默认会自动处理 302 重定向
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            print(f"⚠️ 接口请求失败: Status {resp.status_code}")
            return {}
            
        res_json = resp.json()
        if not res_json or 'data' not in res_json or 'diff' not in res_json['data']:
            print("⚠️ 接口返回数据为空")
            return {}
            
        data_list = res_json['data']['diff']
        print(f"✅ 成功获取 {len(data_list)} 条数据")
        
        for item in data_list:
            # item 示例: {'f12': '600519', 'f14': '贵州茅台', 'f2': 1500.0, ...}
            code = item.get('f12')
            
            # 解析数据 (注意处理无效值 - )
            def parse_float(val):
                if val == '-' or val is None: return 0.0
                try: return float(val)
                except: return 0.0

            price = parse_float(item.get('f2'))
            pe = parse_float(item.get('f9'))
            pb = parse_float(item.get('f23'))
            
            # 股息率: 优先取 f133(港股/部分A), 如果为0则取 f115(A股)
            dv = parse_float(item.get('f133'))
            if dv == 0:
                dv = parse_float(item.get('f115'))
                
            data_map[code] = {
                'price': price,
                'pe_ttm': pe,
                'pb': pb,
                'dv_ratio': dv
            }
            
    except Exception as e:
        print(f"❌ 数据拉取异常: {e}")
        # 这里可以考虑增加重试逻辑
        
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
    
    # 添加图例说明
    lines.append("图例: 🔥极低估值 | ✅低估 | ⚖️合理 | ⚠️风险 | 🔴高估")
    lines.append("-" * 30)
    
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
                    elif pct > 80: icon = "⚠️" # 风险
                    elif pct > 100: icon = "🔴" # 高估
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
