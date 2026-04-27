# main.py
import asyncio
import yaml
import logging
import random
from skland_api import SklandAPI
from notifier import NotifierManager

# 初始化基础日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SklandStandalone")

async def run_sign_in():
    # 1. 加载配置
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("找不到 config.yaml 文件")
        return

    # 2. 日志等级控制
    user_log_level = config.get("log_level", "info").lower()
    # 调整底层库日志等级
    for lib in ["httpx", "httpcore", "skland_api", "Qmsg"]:
        lib_logger = logging.getLogger(lib)
        lib_logger.setLevel(logging.INFO if user_log_level == "debug" else WARNING)

    users = config.get("users", [])

    if not users:
        logger.warning("配置中没有发现用户信息")
        return

    # ================== 【新增：全局随机延时防风控】 ==================
    # 获取配置，未配置或格式错误则默认 120 秒
    random_sleep_range = config.get("RANDOM_SLEEP_SECS_RANGE", 120)
    try:
        random_sleep_range = int(random_sleep_range)
    except (ValueError, TypeError):
        random_sleep_range = 120

    # 限制范围在 0-600 秒之间
    random_sleep_range = max(0, min(600, random_sleep_range))

    if random_sleep_range > 0:
        sleep_time = random.randint(1, random_sleep_range)
        logger.info(f"开启防风控随机延时，本次将等待 {sleep_time} 秒后开始...")
        await asyncio.sleep(sleep_time)
    else:
        logger.info("随机延时已配置为 0，将立即执行签到...")
    # ==================================================================

    api = SklandAPI(max_retries=3)
    notifier = NotifierManager(config)
    
    # 3. 准备消息头部
    # 格式要求: 📅 森空岛签到姬
    notify_lines = ["📅 森空岛签到姬", ""] # 空字符串用于换行
    
    logger.info(f"开始执行签到任务，共 {len(users)} 个账号")
    
    # ================== 【提前获取设备指纹 (防风控献祭)】 ==================
    logger.info("正在初始化设备指纹...")
    did_success = False
    for attempt in range(1, 4):  # 最多尝试 3 次获取设备 ID
        try:
            # 提前调用获取设备 ID，如果成功，会被 api 实例缓存在 self._did 中
            await api.get_device_id()
            did_success = True
            logger.info("设备指纹初始化成功！")
            break
        except Exception as e:
            logger.warning(f"获取设备指纹失败 (尝试 {attempt}/3): {e}")
            if attempt < 3:
                await asyncio.sleep(5)  # 失败后等待 5 秒再试，避开并发高峰

    # 如果重试了 3 次依然失败，直接终止程序，不执行后续签到
    if not did_success:
        error_msg = "❌ 致命错误: 连续 3 次无法获取设备指纹 (可能触发风控)，本次签到任务已全部取消。"
        logger.error(error_msg)
        notify_lines.append(error_msg)
        
        # 发送失败通知并退出
        final_message = "\n".join(notify_lines)
        await notifier.send_all(final_message)
        await api.close()
        return
    # ==================================================================

    # 遍历用户，使用 enumerate 获取序号 (从1开始)
    for index, user in enumerate(users, 1):
        nickname_cfg = user.get("nickname", "未知用户")
        token = user.get("token")
        
        # 从配置中读取 game_type，如果没有配置则默认为 0 (全部签到)
        # 0=全部, 1=仅明日方舟, 2=仅终末地
        game_type = int(user.get("game_type", 0)) 
        
        # 格式要求: 🌈 No.1(nickname1):
        user_header = f"🌈 No.{index}({nickname_cfg}):"
        notify_lines.append(user_header)
        logger.info(f"正在处理: {nickname_cfg}")

        if not token:
            logger.error(f"  [{nickname_cfg}] 未配置 Token")
            notify_lines.append("❌ 账号配置错误: 缺少Token")
            notify_lines.append("") 
            continue
            
        try:
            # 执行签到 (传入 game_type 参数)
            results, official_nickname = await api.do_full_sign_in(token, game_type)
            
            if not results:
                notify_lines.append("❌ 未找到绑定角色")
                logger.warning(f"  [{nickname_cfg}] 未找到角色")
            
            for r in results:
                # 状态判定逻辑
                # 成功 -> ✅, 成功 (奖励)
                # 已签到 -> ✅, 已签
                # 失败 -> ❌, 失败 (原因)
                
                is_signed_already = not r.success and any(k in r.error for k in ["已签到", "重复", "already"])
                
                if r.success:
                    icon = "✅"
                    status_text = "成功"
                    # 如果有奖励，显示具体奖励；否则留空
                    detail = f" ({', '.join(r.awards)})" if r.awards else ""
                elif is_signed_already:
                    icon = "✅"
                    status_text = "已签"
                    detail = ""
                else:
                    icon = "❌"
                    status_text = "失败"
                    detail = f" ({r.error})"

                # 拼接单行: ✅ 明日方舟: 成功 (龙门币x500)
                line = f"{icon} {r.game}: {status_text}{detail}"
                notify_lines.append(line)
                
                # 控制台输出简单日志
                logger.info(f"  - {line}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"  [{nickname_cfg}] 异常: {error_msg}")
            notify_lines.append(f"❌ 系统错误: {error_msg}")

        # 每个用户结束后加个空行，美观
        notify_lines.append("")

    await api.close()
    
    # 4. 发送推送
    while notify_lines and notify_lines[-1] == "":
        notify_lines.pop()

    final_message = "\n".join(notify_lines)
    await notifier.send_all(final_message)
        
    logger.info("所有任务已完成")

# 补充缺失的常量定义 (防止上面代码报错)
WARNING = logging.WARNING

if __name__ == "__main__":
    asyncio.run(run_sign_in())