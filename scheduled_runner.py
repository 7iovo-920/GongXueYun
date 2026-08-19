import logging
import argparse
import time
import threading
from datetime import datetime, timedelta, time as dt_time
from typing import List, Optional

# 导入主任务执行函数
from main import execute_tasks

# 尝试导入主模块的日志上下文，失败则创建本地版本
try:
    from main import _log_ctx
except ImportError:
    _log_ctx = threading.local()

logger = logging.getLogger("scheduler")

# 设置调度器的日志标签
_log_ctx.tag = "SCHEDULER"

# 打卡时间窗口：
# 上班：严格在 09:00 之前执行
# 下班：严格在 17:00 之后执行
MORNING_CUTOFF = dt_time(9, 0)
EVENING_CUTOFF = dt_time(17, 0)


def sleep_until(target: datetime) -> bool:
    """休眠直到指定时间。返回 False 表示收到 Ctrl+C。"""
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return True

        try:
            # 最长每次睡眠 60 秒，方便 Ctrl+C 及时退出。
            time.sleep(min(60, remaining))
        except KeyboardInterrupt:
            logger.info("收到中断信号，退出调度器")
            return False


def execute_once(label: str, selected_files: Optional[List[str]]) -> bool:
    """执行一次主任务。返回 True 表示调度器继续运行。"""
    logger.info(f"开始执行{label}任务")
    try:
        execute_tasks(selected_files)
        logger.info(f"{label}任务执行完成")
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出调度器")
        return False
    except Exception as e:
        # 主任务异常不会导致调度器退出，下一时间窗口仍可继续运行。
        logger.exception(f"{label}任务执行时发生异常: {e}")
    return True


def run_loop(selected_files: Optional[List[str]]):
    """主循环：每天上班、下班各执行一次。"""
    current_day = datetime.now().date()
    morning_done = False
    evening_done = False

    logger.info("调度器启动")
    logger.info("规则：09:00之前执行上班打卡，17:00之后执行下班打卡")

    while True:
        now = datetime.now()

        # 跨天后重置当天执行状态。
        if now.date() != current_day:
            current_day = now.date()
            morning_done = False
            evening_done = False
            logger.info(f"进入新的一天：{current_day}，重置执行状态")

        current_time = now.time()

        # ------------------------------------------------------------
        # 1. 上班打卡窗口：程序启动后如果还没到 09:00，立即执行一次。
        #    如果 09:00 以后才启动，则跳过当天上班打卡，等待下班窗口。
        # ------------------------------------------------------------
        if not morning_done and current_time < MORNING_CUTOFF:
            logger.info(
                f"当前时间 {now.strftime('%H:%M:%S')} < 09:00，执行今天的上班打卡"
            )
            if not execute_once("上班打卡", selected_files):
                return
            morning_done = True
            continue

        if not morning_done and current_time >= MORNING_CUTOFF and current_time < EVENING_CUTOFF:
            evening_target = datetime.combine(current_day, EVENING_CUTOFF)
            logger.info(
                f"已超过上班打卡时间，今天不再执行上班打卡；"
                f"下一次执行时间：{evening_target.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if not sleep_until(evening_target):
                return
            continue

        # ------------------------------------------------------------
        # 2. 下班打卡窗口：17:00之后执行一次。
        # ------------------------------------------------------------
        if not evening_done and current_time >= EVENING_CUTOFF:
            logger.info(
                f"当前时间 {now.strftime('%H:%M:%S')} >= 17:00，执行今天的下班打卡"
            )
            if not execute_once("下班打卡", selected_files):
                return
            evening_done = True

            # 下班任务完成后，暂停到第二天 08:59:59。
            next_day = current_day + timedelta(days=1)
            next_morning = datetime.combine(
                next_day, MORNING_CUTOFF
            ) - timedelta(seconds=1)
            logger.info(
                f"今天的上、下班任务均已处理，暂停到下一天："
                f"{next_morning.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if not sleep_until(next_morning):
                return
            continue

        # ------------------------------------------------------------
        # 3. 正常情况下执行到这里，说明当天两个任务都已经完成。
        #    等待第二天 08:59:59，然后由下一轮循环立即执行上班打卡。
        # ------------------------------------------------------------
        next_day = current_day + timedelta(days=1)
        next_morning = datetime.combine(
            next_day, MORNING_CUTOFF
        ) - timedelta(seconds=1)
        logger.info(
            f"当天任务已完成，等待下一天：{next_morning.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if not sleep_until(next_morning):
            return


def main():
    parser = argparse.ArgumentParser(
        description="定时调度脚本：09:00前执行上班打卡，17:00后执行下班打卡"
    )
    parser.add_argument(
        "--file",
        type=str,
        nargs="+",
        help="指定要执行的配置文件名（不带路径和后缀），透传给主程序",
    )
    args = parser.parse_args()

    logger.info("调度器启动完成")
    try:
        run_loop(args.file)
    except KeyboardInterrupt:
        logger.info("调度器已退出")


if __name__ == "__main__":
    main()
