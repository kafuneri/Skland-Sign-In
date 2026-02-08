# main.py
import asyncio
import yaml
import logging
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

    api = SklandAPI(max_retries=3)
    notifier = NotifierManager(config)
    
    # 3. 准备消息头部
    # 格式要求: 📅 森空岛签到姬
    notify_lines = ["📅 森空岛签到姬", ""] # 空字符串用于换行
    
    logger.info(f"开始执行签到任务，共 {len(users)} 个账号")
    
    # 遍历用户，使用 enumerate 获取序号 (从1开始)
    for index, user in enumerate(users, 1):
        nickname_cfg = user.get("nickname", "未知用户")
        token = user.get("token")
        
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
            # 执行签到
            results, official_nickname = await api.do_full_sign_in(token)
            
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