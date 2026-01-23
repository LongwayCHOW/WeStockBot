# 文件名: evening_push.py
import akshare as ak
import pandas as pd
import datetime
import requests
import os
import re

# 1. 获取 Key
KEYS_STR = os.getenv("SERVERCHAN_KEY", "")

# 2. 辅助函数：将中文单位(亿/万)转换为数字(亿元)
def parse_money(value):
    try:
        # 如果已经是数字
        if isinstance(value, (int, float)):
            return float(value) / 1e8
        
        # 如果是字符串，处理单位
        str_val = str(value)
        if '亿' in str_val:
            return float(str_val.replace('亿', '')) 
        elif '万' in str_val:
            return float(str_val.replace('万', '')) / 10000
        else:
            return float(str_val) / 1e8
    except:
        return 0.0

def get_market_analysis():
    print("🌙 正在生成【A股复盘】(CSV持久化版)...")
    summary_lines = []
    
    # 定义 CSV 路径
    csv_path = os.path.join("data", "history_fund_flow.csv")
    
    try:
        # 1. 获取今日数据
        df_today = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 2. 清洗今日数据
        # 提取需要的列：名称, 涨跌幅, 主力净流入
        name_col = next((x for x in df_today.columns if "名称" in x), "名称")
        pct_col = next((x for x in df_today.columns if "涨跌幅" in x), "今日涨跌幅")
        flow_col = next((x for x in df_today.columns if "主力净流入" in x), "今日主力净流入")
        
        # 整理成标准格式 List[Dict]
        today_records = []
        for _, row in df_today.iterrows():
            today_records.append({
                "date": today_str,
                "name": row[name_col],
                "pct": float(str(row[pct_col]).replace('%','')),
                "flow": parse_money(row[flow_col])
            })
            
        # 3. 读取并更新 CSV
        if os.path.exists(csv_path):
            df_hist = pd.read_csv(csv_path)
            # 删除今天已有的数据（防止重复运行导致重复）
            df_hist = df_hist[df_hist['date'] != today_str]
        else:
            df_hist = pd.DataFrame(columns=["date", "name", "pct", "flow"])
            
        # 合并
        df_new = pd.DataFrame(today_records)
        df_final = pd.concat([df_hist, df_new], ignore_index=True)
        
        # 保存回 CSV
        df_final.to_csv(csv_path, index=False)
        print(f"✅ 数据已更新至 {csv_path}")
        
        # 4. 生成最近 5 个交易日的报告
        # 获取所有唯一的日期，并倒序排列
        all_dates = sorted(df_final['date'].unique(), reverse=True)
        recent_dates = all_dates[:5] # 取最近 5 天
        
        for date_str in recent_dates:
            # 筛选该日数据
            day_data = df_final[df_final['date'] == date_str]
            
            # 找出领涨 Top 3
            top_gainers = day_data.sort_values(by='pct', ascending=False).head(3)
            # 找出流入 Top 3
            top_flows = day_data.sort_values(by='flow', ascending=False).head(3)
            
            summary_lines.append(f"� **{date_str}**")
            
            line_gainers = []
            for _, row in top_gainers.iterrows():
                line_gainers.append(f"{row['name']} {row['pct']}%")
            summary_lines.append(f"🔥 领涨: {', '.join(line_gainers)}")
            
            line_flows = []
            for _, row in top_flows.iterrows():
                line_flows.append(f"{row['name']} {row['flow']:+.1f}亿")
            summary_lines.append(f"💰 抢筹: {', '.join(line_flows)}")
            
            summary_lines.append("")
            
        # 生成标题
        title = f"A股复盘: {today_str} (近{len(recent_dates)}日追踪)"
        content = "\n".join(summary_lines)
        return title, content

    except Exception as e:
        import traceback
        traceback.print_exc()
        return "分析失败", f"数据解析错误: {str(e)}"

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
    title, content = get_market_analysis()
    print("----------------")
    print(title)
    print(content)
    print("----------------")
    push_to_wechat(title, content)
