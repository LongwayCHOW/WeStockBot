# 文件名: evening_push.py
import requests
import pandas as pd
import datetime
import os
import json
import re

# 1. 获取 Key
KEYS_STR = os.getenv("SERVERCHAN_KEY", "")

def get_market_analysis():
    print("🌙 正在生成【A股复盘】(Sina版)...")
    summary_lines = []
    
    # 定义 CSV 路径 (使用新文件以区分旧数据源)
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    csv_path = os.path.join(data_dir, "history_sector_sina.csv")
    
    try:
        # 1. 获取今日数据 (Sina 行业板块)
        url = "http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
        resp = requests.get(url, timeout=10)
        # Sina 接口通常是 GBK 编码
        text = resp.content.decode('gbk', errors='ignore')
        
        # 解析 JSON: var S_Finance_bankuai_sinaindustry = {...}
        # 提取 {...} 部分
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx == -1 or end_idx == -1:
            return "分析失败", "数据解析错误: 无法找到JSON数据"
            
        json_str = text[start_idx:end_idx+1]
        data_dict = json.loads(json_str)
        
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        today_records = []
        
        # 2. 清洗数据
        # Format: "code,Name,Count,AvgPrice,ChangeAmt,ChangePct,Volume,Amount,LeaderCode,LeaderPct,LeaderPrice,LeaderChange,LeaderName"
        for key, val_str in data_dict.items():
            parts = val_str.split(',')
            if len(parts) < 13: continue
            
            name = parts[1]
            pct = float(parts[5])
            amount = float(parts[7]) / 1e8 # 转为亿元
            leader_name = parts[12]
            leader_pct = float(parts[9])
            
            today_records.append({
                "date": today_str,
                "name": name,
                "pct": pct,
                "amount": amount,
                "leader": leader_name,
                "leader_pct": leader_pct
            })
            
        # 转为 DataFrame
        df_new = pd.DataFrame(today_records)
        
        # 3. 读取并更新 CSV
        if os.path.exists(csv_path):
            df_hist = pd.read_csv(csv_path)
            # 删除今天已有的数据
            df_hist = df_hist[df_hist['date'] != today_str]
        else:
            df_hist = pd.DataFrame(columns=["date", "name", "pct", "amount", "leader", "leader_pct"])
            
        # 合并
        df_final = pd.concat([df_hist, df_new], ignore_index=True)
        
        # 保存回 CSV
        df_final.to_csv(csv_path, index=False)
        print(f"✅ 数据已更新至 {csv_path}")
        
        # 4. 生成最近 5 个交易日的报告
        all_dates = sorted(df_final['date'].unique(), reverse=True)
        recent_dates = all_dates[:5] 
        
        for date_str in recent_dates:
            day_data = df_final[df_final['date'] == date_str]
            
            # 找出领涨 Top 5
            top_gainers = day_data.sort_values(by='pct', ascending=False).head(5)
            # 找出成交额 Top 3 (热度)
            top_amounts = day_data.sort_values(by='amount', ascending=False).head(3)
            
            summary_lines.append(f"📅 **{date_str}**")
            
            # 领涨板块 + 龙头
            line_gainers = []
            for _, row in top_gainers.iterrows():
                # 格式: 行业(2.5%) 
                # 简化显示，避免过长
                line_gainers.append(f"{row['name']}({row['pct']}%)")
            summary_lines.append(f"🔥 领涨: {', '.join(line_gainers)}")
            
            # 热门板块 (成交额)
            line_amounts = []
            for _, row in top_amounts.iterrows():
                line_amounts.append(f"{row['name']}({row['amount']:.0f}亿)")
            summary_lines.append(f"💰 热门: {', '.join(line_amounts)}")
            
            # 龙头股展示 (取 Top 3 领涨板块的龙头)
            top3_gainers = top_gainers.head(3)
            leaders = []
            for _, row in top3_gainers.iterrows():
                leaders.append(f"{row['leader']} {row['leader_pct']}%")
            summary_lines.append(f"👑 龙头: {', '.join(leaders)}")
            
            summary_lines.append("")
            
        # 生成标题
        title = f"A股复盘: {today_str} (Sina版)"
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
