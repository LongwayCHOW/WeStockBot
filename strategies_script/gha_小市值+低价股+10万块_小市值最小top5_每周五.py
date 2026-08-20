# ==============================================================================
# GitHub Action 实盘选股脚本 —— 小市值最小 top5（每周五）
# ------------------------------------------------------------------------------
# 来源策略：strategies/小市值+低价股+10万块/小市值+低价股+10万块.py
# 对应分支：Branch 2「小市值10%+低价 top 5」（用户口径：小市值最小 top5）
#           （分支参数 top_n=5, max_gross_margin=100, min_eps=None 已固化）
# 调仓频率：每周五收盘后运行（用户自定义；回测原为每月最后交易日 last_of_month）
# 运行环境：用户其他 GitHub 项目的 GitHub Action（本脚本自包含，不依赖本地模块）
# 目标    ：按策略分支公式选股，输出与回测引擎同口径的选股清单
#
# 与回测一致的口径说明（重要）：
#   1. 回测调仓日 T 的截面 = "T-1 收盘可见数据"（DataLoader shift(1)）：
#      close_lag1 = 最近收盘价（T-1 收盘），total_mv 应为「昨收价 × 总股本」口径
#   2. 回测引擎在 rebalance 前有 FilterPipeline 六道硬过滤（ST/退市/停牌/涨停/
#      上市180天/科创688），本脚本已同口径转化；数据缺列时对应过滤自动跳过并告警
#   3. 选股公式与策略 rebalance 完全一致（close_lag1>=2元 → 市值最小10% → 低价 top5）
#
# 数据契约（输入 CSV，UTF-8，表头英文）：
#   code         必填  6 位股票代码（如 600519）
#   close_lag1   必填  昨收价（最近收盘价，与回测 raw_close.shift(1) 同口径）
#   total_mv     必填  总市值（单位：元；请用「昨收价 × 总股本」口径，与回测一致）
#   name         可选  股票名称（is_st 缺失时用于 ST 识别兜底）
#   is_st        可选  1/0 是否 ST（回测硬过滤）
#   is_susp      可选  1/0 是否停牌（回测硬过滤）
#   is_wd        可选  1/0 是否退市（回测硬过滤）
#   high_limited 可选  涨停价（回测硬过滤：昨收价 >= 涨停价视为涨停不可买）
#   listed_date  可选  上市日期 YYYY-MM-DD（上市不足 180 天剔除）
#
# 用法：
#   python gha_小市值+低价股+10万块_小市值最小top5_每周五.py \
#       --input 行情.csv [--as-of 2026-08-14] [--output 选股清单.json] [--force]
#   --force 跳过「周五」检查（调试用）；非周五默认打印提示并以退出码 0 结束
# ==============================================================================

import argparse
import json
import sys
from datetime import date, datetime

import pandas as pd

# ==============================================================================
# 策略参数（转化自 strategies/小市值+低价股+10万块/小市值+低价股+10万块.py
#          的 Branch 2「小市值10%+低价 top 5」分支 params，固化不变量）
# ==============================================================================

#1
#选股参数（来源：策略 PARAMS + Branch 2 分支 params 合并结果）
#说明：max_gross_margin=100（不筛毛利率）、min_eps=None（不筛 eps）为该分支特性
PARAMS = {
    'top_n': 5,            # 持仓数量：低价 top 5
    'max_gross_margin': 100,  # 最高毛利率筛选 %（100 = 不筛选）
    'min_eps': None,       # 最低 eps 筛选（None = 不筛选）
    'mv_percentile': 10,   # 市值分位阈值 %：取市值最小的 10%
    'min_stocks': 10,      # 最低可选股票数：不足则放弃本次调仓
}

# ==============================================================================
# 数据加载
# ==============================================================================

#1
#读取行情 CSV 并标准化
#输入：path (str) - CSV 文件路径
#输出：pd.DataFrame - 索引为 6 位 code，含契约列；同时返回缺失列告警列表
#说明：code 统一 zfill(6)；数值列转 float；缺列不报错，返回告警由过滤链降级处理
def load_market_data(path: str) -> tuple[pd.DataFrame, list[str]]:
    REQUIRED = ['code', 'close_lag1', 'total_mv']
    OPTIONAL = ['name', 'is_st', 'is_susp', 'is_wd', 'high_limited', 'listed_date']

    df = pd.read_csv(path, dtype={'code': str})
    warnings = []

    # 必填列校验：缺任何必填列直接终止
    missing_req = [c for c in REQUIRED if c not in df.columns]
    if missing_req:
        raise ValueError(f'CSV 缺少必填列: {missing_req}，契约见文件头注释')

    # 可选列缺失 → 记告警（对应过滤跳过，与回测一致性降级）
    missing_opt = [c for c in OPTIONAL if c not in df.columns]
    if missing_opt:
        warnings.append(f'可选列缺失: {missing_opt}，对应过滤已跳过（与回测一致性降级，请补数据）')

    # 代码标准化 + 索引用 code
    df['code'] = df['code'].astype(str).str.strip().str.zfill(6)
    df = df.set_index('code')

    # 数值列转 float（非数值行置 NaN，由基础过滤剔除）
    for col in ['close_lag1', 'total_mv'] + [c for c in OPTIONAL if c in df.columns and c != 'name' and c != 'listed_date']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'listed_date' in df.columns:
        df['listed_date'] = pd.to_datetime(df['listed_date'], errors='coerce').dt.date

    return df, warnings


# ==============================================================================
# 过滤链（转化自回测引擎 FilterPipeline.apply，六道硬过滤同口径）
# ==============================================================================

#1
#执行与回测同口径的六道硬过滤
#输入：df (pd.DataFrame) - 全市场行情（index=code）
#      as_of (date) - 数据日期（上市天数过滤用）
#输出：pd.DataFrame - 通过过滤的有效股票池（已剔除）
#说明：顺序与回测一致：基础 → 退市 → 上市天数 → 科创 → 涨停/停牌 → ST
#      缺列对应过滤自动跳过（附告警，由调用方汇总）
def apply_filters(df: pd.DataFrame, as_of: date) -> tuple[pd.DataFrame, list[str]]:
    warnings = []
    valid = df.copy()

    # ---- Filter 1: 基础过滤（close_lag1>0 且 total_mv>0）----
    n0 = len(valid)
    valid = valid[(valid['close_lag1'].notna()) & (valid['close_lag1'] > 0) &
                  (valid['total_mv'].notna()) & (valid['total_mv'] > 0)]
    if len(valid) < n0:
        warnings.append(f'基础过滤(close>0+mv>0): 剔除 {n0 - len(valid)} 只')

    # ---- Filter 2: 退市过滤（is_wd=1 剔除；回测 is_wd_sec）----
    if 'is_wd' in valid.columns:
        n1 = len(valid)
        valid = valid[valid['is_wd'].fillna(0) != 1]
        if len(valid) < n1:
            warnings.append(f'退市过滤(is_wd=1): 剔除 {n1 - len(valid)} 只')
    else:
        warnings.append('退市过滤跳过：缺 is_wd 列（退市股不在行情列表则影响小）')

    # ---- Filter 3: 上市天数过滤（>=180 天）----
    if 'listed_date' in valid.columns:
        n2 = len(valid)
        listed_ok = valid['listed_date'].apply(
            lambda ld: pd.isna(ld) or (as_of - ld).days >= 180)
        valid = valid[listed_ok]
        if len(valid) < n2:
            warnings.append(f'上市天数过滤(<180天): 剔除 {n2 - len(valid)} 只')
    else:
        warnings.append('上市天数过滤跳过：缺 listed_date 列')

    # ---- Filter 4: 科创板块过滤（688/689 剔除）----
    n3 = len(valid)
    valid = valid[~valid.index.str.startswith(('688', '689'))]
    if len(valid) < n3:
        warnings.append(f'科创板过滤(688/689): 剔除 {n3 - len(valid)} 只')

    # ---- Filter 5: 涨停/停牌过滤（回测：昨收>=涨停价 或 停牌 → 剔除）----
    if 'high_limited' in valid.columns or 'is_susp' in valid.columns:
        n4 = len(valid)
        limit_mask = pd.Series(True, index=valid.index)
        if 'high_limited' in valid.columns:
            hl = valid['high_limited'].fillna(0)
            limit_mask &= ~((valid['close_lag1'] >= hl) & (hl > 0))
        if 'is_susp' in valid.columns:
            limit_mask &= valid['is_susp'].fillna(0) != 1
        valid = valid[limit_mask]
        if len(valid) < n4:
            warnings.append(f'涨停/停牌过滤: 剔除 {n4 - len(valid)} 只')
    else:
        warnings.append('涨停/停牌过滤跳过：缺 high_limited 和 is_susp 列')

    # ---- Filter 6: ST/*ST 过滤（is_st=1 剔除；缺列用名称含 ST 兜底）----
    n5 = len(valid)
    if 'is_st' in valid.columns:
        valid = valid[valid['is_st'].fillna(0) != 1]
    elif 'name' in valid.columns:
        valid = valid[~valid['name'].fillna('').str.contains('ST')]
    else:
        warnings.append('ST 过滤跳过：缺 is_st 和 name 列（风险高，请补数据）')
    if len(valid) < n5:
        warnings.append(f'ST/*ST 过滤: 剔除 {n5 - len(valid)} 只')

    return valid, warnings


# ==============================================================================
# 选股（转化自 strategies/小市值+低价股+10万块/小市值+低价股+10万块.py
#          的 rebalance 函数，公式保持不变）
# ==============================================================================

#1
#低价 + 小市值选股：市值最小 10% → 股价升序取 top_n → 等权
#输入：valid (pd.DataFrame) - 过滤后的股票池（index=code，含 close_lag1/total_mv）
#      params (dict) - 选股参数（PARAMS）
#输出：pd.DataFrame - 选中股票（含权重列 weight）；选股池不足时返回空表
#说明：与回测 rebalance 逻辑逐行一致：
#      1) close_lag1 >= 2.0 元；min_eps/max_gross_margin 本分支不筛（None/100）
#      2) total_mv <= 市值分位 10%（pandas quantile 线性插值，同回测）
#      3) 按 close_lag1 升序取 top_n，等权 1/top_n
def select_low_price_small_cap(valid: pd.DataFrame, params: dict) -> pd.DataFrame:
    top_n = params['top_n']
    mv_percentile = params['mv_percentile']
    min_stocks = params['min_stocks']

    # 第一步：股价 >= 2 元（回测 mask = snapshot['close_lag1'] >= 2.0）
    pool = valid[valid['close_lag1'] >= 2.0].copy()
    if len(pool) < min_stocks:
        print(f'[WARN] 基础可选股票不足: {len(pool)} < {min_stocks}，本次放弃调仓')
        return pd.DataFrame()

    # 第二步：市值最小的 mv_percentile%（回测 total_mv.quantile(0.10) 线性插值）
    mv_threshold = pool['total_mv'].quantile(mv_percentile / 100.0)
    small_mv = pool[pool['total_mv'] <= mv_threshold].copy()
    if len(small_mv) < min_stocks:
        print(f'[WARN] 小市值候选不足: {len(small_mv)} < {min_stocks}，本次放弃调仓')
        return pd.DataFrame()

    # 第三步：按股价从低到高排序，取 top_n（回测 sort_values('close_lag1', ascending=True)）
    small_mv = small_mv.sort_values('close_lag1', ascending=True)
    selected = small_mv.head(top_n)

    # 等权分配（回测 weight = 1.0 / len(selected)）
    weight = 1.0 / len(selected)
    selected['weight'] = weight
    return selected


# ==============================================================================
# 输出
# ==============================================================================

#1
#格式化选股清单（可读文本 + JSON 结构）
#输入：selected (pd.DataFrame) - 选中股票；df (pd.DataFrame) - 原始全市场
#      meta (dict) - as_of/过滤统计/告警/参数等元信息
#输出：(str, dict) - (可读文本, JSON dict，供 GitHub Action 消费)
def build_output(selected: pd.DataFrame, df: pd.DataFrame, meta: dict) -> tuple[str, dict]:
    lines = []
    lines.append('=' * 60)
    lines.append(f'选股日期: {meta["as_of"]}  ({meta["weekday"]})')
    lines.append(f'来源策略: {meta["strategy"]} → 分支「{meta["branch"]}」')
    lines.append(f'全市场: {meta["raw_count"]} 只 → 过滤后: {meta["valid_count"]} 只')
    lines.append(f'市值分位阈值({meta["mv_percentile"]}%): {meta["mv_threshold"]:,.0f} 元')
    if meta['warnings']:
        lines.append('过滤告警（一致性降级提示）:')
        for w in meta['warnings']:
            lines.append(f'  - {w}')
    if selected.empty:
        lines.append('本次调仓放弃：选股池不足，无买入清单（清仓观望）')
        lines.append('=' * 60)
        return '\n'.join(lines), {'as_of': meta['as_of'], 'selected': [], 'aborted': True}

    lines.append('')
    lines.append('=== 买入清单（次一交易日开盘参考，等权 20% 每只）===')
    for _, row in selected.iterrows():
        name = row.get('name', '')
        lines.append(f'  {row.name} {name:<10} 昨收={row["close_lag1"]:.2f}  '
                     f'总市值={row["total_mv"] / 1e8:,.2f}亿  权重={row["weight"]:.0%}')
    lines.append('=' * 60)

    # 备注：操作提醒（次一交易日开盘买入；ST/退市/停牌/涨停等已在过滤链剔除）
    lines.append('操作提醒：')
    lines.append('  1. 次一交易日（下周一）开盘按清单买入，等权各 20%')
    lines.append('  2. 持仓中如新出现 ST → 尽快卖出；停牌/跌停卖不出则排队后续处理')
    lines.append('  3. 每只买入量建议不超过当日成交量的 5%（防滑点/流动性风险）')
    lines.append('=' * 60)

    selected_list = [
        {
            'code': str(row.name),
            'name': row.get('name', ''),
            'close_lag1': round(float(row['close_lag1']), 4),
            'total_mv': round(float(row['total_mv']), 2),
            'weight': round(float(row['weight']), 6),
        }
        for _, row in selected.iterrows()
    ]
    result = {
        'as_of': meta['as_of'],
        'strategy': meta['strategy'],
        'branch': meta['branch'],
        'params': meta['params'],
        'raw_count': meta['raw_count'],
        'valid_count': meta['valid_count'],
        'mv_threshold': meta['mv_threshold'],
        'filter_warnings': meta['warnings'],
        'selected': selected_list,
        'aborted': False,
    }
    return '\n'.join(lines), result


# ==============================================================================
# 主编排
# ==============================================================================

#1
#判断今天是否周五（GitHub Action cron 双保险）
#输入：today (date)
#输出：bool - 是否周五（weekday()==4）
def is_friday(today: date) -> bool:
    return today.weekday() == 4


#2
#命令行入口
#输入：sys.argv - --input/--as-of/--output/--force
#输出：int - 退出码（0 正常，1 数据错误）
def main() -> int:
    parser = argparse.ArgumentParser(description='GitHub Action 实盘选股（小市值最小 top5，每周五）')
    parser.add_argument('--input', required=True, help='行情 CSV 文件路径（数据契约见文件头注释）')
    parser.add_argument('--as-of', default=None, help='数据日期 YYYY-MM-DD（默认今天）')
    parser.add_argument('--output', default=None, help='选股清单 JSON 输出路径（可选，不写则仅打印）')
    parser.add_argument('--force', action='store_true', help='跳过周五检查（调试用）')
    args = parser.parse_args()

    as_of = datetime.strptime(args.as_of, '%Y-%m-%d').date() if args.as_of else date.today()

    # 周五检查（cron 双保险；--force 跳过）
    if not args.force and not is_friday(as_of):
        print(f'{as_of} 非周五，按规则本周不调仓（下次运行：本周五收盘后）。')
        return 0

    # 数据加载（缺列告警随过滤汇总）
    df, load_warnings = load_market_data(args.input)
    print(f'[INFO] 数据加载: {len(df)} 只, as_of={as_of}')

    # 过滤链（与回测 FilterPipeline 同口径）
    valid, filter_warnings = apply_filters(df, as_of)
    print(f'[INFO] 过滤后股票池: {len(valid)} 只（原始 {len(df)} 只）')

    # 选股（与策略 rebalance 同公式）
    selected = select_low_price_small_cap(valid, PARAMS)
    print(f'[INFO] 选中 {len(selected)} 只')

    # 组装输出
    meta = {
        'as_of': as_of.isoformat(),
        'weekday': '周五' if is_friday(as_of) else '非周五(--force)',
        'strategy': '小市值+低价股+10万块',
        'branch': '小市值10%+低价 top 5',
        'mv_percentile': PARAMS['mv_percentile'],
        'params': PARAMS,
        'raw_count': len(df),
        'valid_count': len(valid),
        'mv_threshold': round(float(valid['total_mv'].quantile(PARAMS['mv_percentile'] / 100.0)), 2) if not valid.empty else 0.0,
        'warnings': load_warnings + filter_warnings,
    }
    text, result = build_output(selected, df, meta)
    print(text)

    # JSON 输出（GitHub Action 后续步骤可解析推送）
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'[INFO] 选股清单 JSON 已写入: {args.output}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
