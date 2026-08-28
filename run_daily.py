# -*- coding: utf-8 -*-
"""
run_daily.py — WeStockBot 统一调度唯一入口

背景: GitHub Actions 的 cron 调度天然不可靠——会错峰延迟数十分钟乃至数小时,
      偶尔甚至整次跳过触发(Weekly Stock Selection Push 曾整周漏跑)。
      本脚本把「今天该跑哪些脚本」的决策收拢到一处:

  daily_orchestrator.yml 每 30 分钟触发一次本脚本,
  脚本对照任务表 TASKS, 判断「当前北京时间此刻该跑哪些任务」:
    - 落在任务窗口内(星期几 + 时间区间) 且当天尚未执行过 → 执行其命令
    - 当天已执行过(仓库内 .run_state.json 有标记) → 跳过, 防窗口内多次触发重复推送
    - 不在窗口 → 本轮空跑, 直接退出

  窗口机制的意义: 每个任务窗口宽 1.5~2 小时, 内含 3~5 个触发候选,
  只要其中一个真正执行, 任务就不会漏跑; 单次调度延迟/丢失不影响最终结果。

新增推送任务的扩展方式(不压缩拓展空间):
    1) 新脚本照老套路写一个独立 workflow(仅 workflow_dispatch, 可手动单独触发)
    2) 在下方 TASKS 增加一条记录(名称/窗口/命令/需提交的产物文件)
    无需改动本脚本的调度逻辑。
"""
import datetime
import json
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# 任务表 (唯一决策依据)
#   days:        None 表示每天; 否则为星期列表 (0=周一 ... 6=周日)
#   window:      (起时, 起分, 止时, 止分), 北京时间, 闭区间
#   cmd:         任务主命令(bash); 失败会让本任务标红, 且不写"已执行"标记,
#                窗口内下一次触发会自动重试
#   push_paths:  执行成功后需要 commit+push 的产物路径(图床/数据文件, 可为空)
#   after_cmd:   可选, 在产物已 push 上线后才执行的第二阶段命令
#                (目前仅 commodity 需要: 图表必须先上线, --push-only 才能引用外链)
# ---------------------------------------------------------------------------
TASKS = [
    {
        # 每日期货走势图 (原 daily_commodity.yml)
        "name": "commodity",
        "days": None,
        "window": (7, 30, 11, 30),                 # 北京时间 07:30 起; 窗口放宽到中午, 产物是历史走势图无时效性
                    # (GitHub cron 实测可延迟数小时, 窗口内每次触发都是候选)
        "cmd": "python commodity_curve.py --render-only",
        "push_paths": ["charts/", "index.html"],
        "after_cmd": "python commodity_curve.py --push-only",
    },
    {
        # 每周五选股推送 (原 daily_selection.yml), 维持周五早 08:00 时段
        "name": "weekly_selection",
        "days": [4],                              # 仅周五
        "window": (8, 0, 12, 0),                  # 周五 08:00 起 (保持原时段语义); 窗口放宽到中午, 防 cron 延迟导致当日漏跑
        "cmd": (
            "python strategies_script/fetch_a_share_snapshot.py --output data/a_share_snapshot.csv && "
            'python "strategies_script/gha_小市值+低价股+10万块_小市值最小top5_每周五.py" '
            '--input data/a_share_snapshot.csv --as-of "$(date +%F)" --output data/selection.json && '
            "python strategies_script/push_selection.py --input data/selection.json"
        ),
        "push_paths": [],
        "after_cmd": None,
    },
    {
        # 午间估值雷达 (原 daily_noon.yml)
        "name": "noon_valuation",
        "days": None,
        "window": (13, 0, 15, 0),                 # 北京时间 13:00 起
        "cmd": "python noon_valuation.py",
        "push_paths": [],
        "after_cmd": None,
    },
    {
        # A股晚间复盘 (原 daily_evening.yml)
        "name": "evening_ashare",
        "days": None,
        "window": (16, 35, 18, 30),               # 北京时间 16:35 起
        "cmd": "python evening_push.py",
        "push_paths": ["data/history_sector_sina.csv"],
        "after_cmd": None,
    },
]

STATE_FILE = ".run_state.json"   # 记录各任务当天是否已执行 (跨 run 防重, 随产物一起 push)
GIT_USER = "github-actions[bot]"


# ------------------------------- 工具函数 ----------------------------------
def shanghai_now():
    """获取当前北京时间(上海时区)。"""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        # 兜底: 依赖进程 TZ 环境变量 (Actions 中已设 TZ=Asia/Shanghai)
        return datetime.datetime.now()


def in_window(now, task):
    """判断当前时刻是否落在任务窗口内(星期几 + 时间闭区间)。"""
    days = task["days"]
    if days is not None and now.weekday() not in days:
        return False
    cur = now.hour * 60 + now.minute
    s_h, s_m, e_h, e_m = task["window"]
    return s_h * 60 + s_m <= cur <= e_h * 60 + e_m


def load_state():
    """读取上次各任务的"已执行"标记; 文件缺失/损坏时视为未执行。"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    """把各任务"已执行"标记写回本地文件(随下一次 push 一起上仓库)。"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_cmd(cmd):
    """在 bash 中执行命令(输出直接透传到 Actions 日志), 返回是否成功。"""
    print(f">>> {cmd}")
    return subprocess.run(cmd, shell=True).returncode == 0


def git_ok(args):
    """执行 git 命令并返回是否成功(吞掉输出, 关键时报错信息打印)。"""
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if p.returncode != 0 and p.stderr.strip():
        print(f"⚠️ git {args[0]}: {p.stderr.strip()[:200]}")
    return p.returncode == 0


def push_changes(push_paths):
    """把已执行任务的标记 + 产物 commit 并 push, 带 rebase 竞态容错与重试。"""
    subprocess.run(["git", "add", STATE_FILE, *push_paths],
                   capture_output=True, text=True)
    # 没有内容变化则无需提交(例如产物恰好与上次相同)
    if git_ok(["diff", "--quiet"]) and git_ok(["diff", "--cached", "--quiet"]):
        print("✅ 无内容变化, 跳过提交")
        return True
    ok = git_ok([
        "-c", f"user.name={GIT_USER}",
        "-c", f"user.email={GIT_USER}@users.noreply.github.com",
        "commit", "-m", "chore: 每日调度产物 [skip ci]",
    ])
    if not ok:
        print("❌ commit 失败")
        return False
    for attempt in range(1, 4):   # 与手动推送竞态时重试: pull --rebase 后 push
        print(f"🌐 push 尝试 {attempt}/3 ...")
        ok = git_ok(["pull", "--rebase", "origin", "main"]) and git_ok(["push"])
        if ok:
            print("✅ push 成功")
            return True
        git_ok(["rebase", "--abort"])   # 冲突则放弃本次 rebase, 交由下次重试
    print("⚠️ 连续 push 失败(竞态), 已跳过; 窗口内下一次触发会重新判定并续跑")
    return False


def main():
    now = shanghai_now()
    today = now.strftime("%Y-%m-%d")
    print(f"== 调度器运行: 北京时间 {now.strftime('%Y-%m-%d %H:%M %A')} ==")

    # 开工前同步最新状态(他人 push 的新标记/新代码), 失败静默(本地工作树此刻是干净的)
    git_ok(["pull", "--rebase", "origin", "main"])

    state = load_state()

    # 决策: 当前时刻该跑哪些任务 (窗口内 + 当天未执行)
    due = [t for t in TASKS if in_window(now, t) and state.get(t["name"]) != today]
    if not due:
        print("⏳ 当前不在任何任务窗口(或今日任务均已执行), 本轮空跑")
        return 0

    failed = []
    for task in due:
        print(f"\n===== ▶ 执行任务: {task['name']} =====")
        if not run_cmd(task["cmd"]):
            failed.append(task["name"])
            print(f"❌ 任务 {task['name']} 主命令失败, 不标记已执行, 窗口内将自动重试")
            continue
        # 执行成功: 先标记"今天已跑"并随产物一起上仓库, 防窗口内重复推送
        state[task["name"]] = today
        save_state(state)
        if not push_changes(task["push_paths"]):
            failed.append(task["name"])
            continue
        if task["after_cmd"]:
            print(f"===== ▶ 任务 {task['name']} 第二阶段(产物已上线推送): =====")
            if not run_cmd(task["after_cmd"]):
                # 产物已上线但不推送微信: 已标记完成, 标红提醒人工处理
                failed.append(task["name"])
                continue
        print(f"✅ 任务 {task['name']} 完成")

    # 任一任务失败 → 整次运行标红, 便于在 GitHub Actions UI 第一时间发现
    if failed:
        print(f"\n❌ 本次调度有任务失败: {failed}")
        return 1
    print("\n✅ 本次调度全部完成")
    return 0


if __name__ == "__main__":
    # 显式退出码(空跑=0, 有任务失败=1), 供 Actions 判色
    sys.exit(main())