# notifier.py
import httpx
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger("notifier")


class NotifierManager:
    """统一通知管理器，根据配置自动选择可用的推送渠道"""

    def __init__(self, config: dict):
        self.notifiers = []
        notify_cfg = config.get("notify", {})

        # 按顺序注册各渠道，只有配置了关键字段才会启用
        if notify_cfg.get("qmsg", {}).get("key"):
            self.notifiers.append(QmsgNotifier(notify_cfg["qmsg"]))

        if notify_cfg.get("onebot", {}).get("url"):
            self.notifiers.append(OneBotNotifier(notify_cfg["onebot"]))

        if notify_cfg.get("email", {}).get("smtp_host"):
            self.notifiers.append(EmailNotifier(notify_cfg["email"]))

        if notify_cfg.get("wecom", {}).get("webhook_url"):
            self.notifiers.append(WeComNotifier(notify_cfg["wecom"]))

        if notify_cfg.get("wechat_mp", {}).get("app_id"):
            self.notifiers.append(WeChatMPNotifier(notify_cfg["wechat_mp"]))

        if notify_cfg.get("serverchan", {}).get("send_key"):
            self.notifiers.append(ServerChanNotifier(notify_cfg["serverchan"]))

        if not self.notifiers:
            logger.info("未配置任何通知渠道，跳过推送")

    async def send_all(self, message: str):
        """向所有已启用的渠道发送通知"""
        if not self.notifiers:
            return

        for notifier in self.notifiers:
            try:
                await notifier.send(message)
            except Exception as e:
                logger.error(f"[{notifier.name}] 推送异常: {e}")


class BaseNotifier:
    """通知基类"""
    name = "base"

    async def send(self, message: str) -> bool:
        raise NotImplementedError


# ==================== Qmsg 酱 ====================
class QmsgNotifier(BaseNotifier):
    name = "Qmsg"

    def __init__(self, cfg: dict):
        self.key = cfg["key"]
        self.base_url = cfg.get("base_url", "https://qmsg.zendee.cn")

    async def send(self, message: str) -> bool:
        url = f"{self.base_url}/send/{self.key}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data={"msg": message})
            result = resp.json()
            if result.get("success"):
                logger.info("[Qmsg] 推送成功")
                return True
            else:
                logger.error(f"[Qmsg] 推送失败: {result.get('reason')}")
                return False


# ==================== OneBot V11 (NapCat等) ====================
class OneBotNotifier(BaseNotifier):
    name = "OneBot"

    def __init__(self, cfg: dict):
        self.url = cfg["url"].rstrip("/")
        self.access_token = cfg.get("access_token", "")
        # 支持多个私聊目标
        self.private_ids = self._parse_ids(cfg.get("private_ids", []))
        # 支持多个群聊目标
        self.group_ids = self._parse_ids(cfg.get("group_ids", []))

    @staticmethod
    def _parse_ids(raw) -> list[int]:
        """将配置值统一解析为 int 列表，支持单个值或列表"""
        if not raw:
            return []
        if isinstance(raw, (int, str)):
            raw = [raw]
        return [int(i) for i in raw if str(i).strip()]

    async def send(self, message: str) -> bool:
        if not self.private_ids and not self.group_ids:
            logger.error("[OneBot] 未配置 private_ids 或 group_ids")
            return False

        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        all_success = True

        async with httpx.AsyncClient() as client:
            # 发送私聊
            for user_id in self.private_ids:
                try:
                    resp = await client.post(
                        f"{self.url}/send_private_msg",
                        json={"user_id": user_id, "message": message},
                        headers=headers,
                    )
                    result = resp.json()
                    if result.get("status") == "ok" or result.get("retcode") == 0:
                        logger.info(f"[OneBot] 私聊推送成功 -> {user_id}")
                    else:
                        logger.error(f"[OneBot] 私聊推送失败 -> {user_id}: {result}")
                        all_success = False
                except Exception as e:
                    logger.error(f"[OneBot] 私聊推送异常 -> {user_id}: {e}")
                    all_success = False

            # 发送群聊
            for group_id in self.group_ids:
                try:
                    resp = await client.post(
                        f"{self.url}/send_group_msg",
                        json={"group_id": group_id, "message": message},
                        headers=headers,
                    )
                    result = resp.json()
                    if result.get("status") == "ok" or result.get("retcode") == 0:
                        logger.info(f"[OneBot] 群聊推送成功 -> {group_id}")
                    else:
                        logger.error(f"[OneBot] 群聊推送失败 -> {group_id}: {result}")
                        all_success = False
                except Exception as e:
                    logger.error(f"[OneBot] 群聊推送异常 -> {group_id}: {e}")
                    all_success = False

        return all_success

# ==================== 邮件 ====================
class EmailNotifier(BaseNotifier):
    name = "Email"

    def __init__(self, cfg: dict):
        self.smtp_host = cfg["smtp_host"]
        self.smtp_port = cfg.get("smtp_port", 465)
        self.use_ssl = cfg.get("use_ssl", True)
        self.username = cfg["username"]
        self.password = cfg["password"]
        self.sender = cfg.get("sender", self.username)
        self.receiver = cfg["receiver"]

    async def send(self, message: str) -> bool:
        # 邮件是同步操作，用 asyncio 包装
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_sync, message)

    def _send_sync(self, message: str) -> bool:
        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender
            msg["To"] = self.receiver
            msg["Subject"] = "森空岛签到通知"

            # 将换行转为 HTML <br> 以保持格式
            html_body = message.replace("\n", "<br>")
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()

            server.login(self.username, self.password)
            server.sendmail(self.sender, [self.receiver], msg.as_string())
            server.quit()
            logger.info("[Email] 推送成功")
            return True
        except Exception as e:
            logger.error(f"[Email] 推送失败: {e}")
            return False


# ==================== 企业微信 Webhook ====================
class WeComNotifier(BaseNotifier):
    name = "WeCom"

    def __init__(self, cfg: dict):
        self.webhook_url = cfg["webhook_url"]

    async def send(self, message: str) -> bool:
        payload = {
            "msgtype": "text",
            "text": {"content": message}
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.webhook_url, json=payload)
            result = resp.json()
            if result.get("errcode") == 0:
                logger.info("[WeCom] 推送成功")
                return True
            else:
                logger.error(f"[WeCom] 推送失败: {result.get('errmsg')}")
                return False


# ==================== 微信服务号 (公众号模板消息) ====================
class WeChatMPNotifier(BaseNotifier):
    name = "WeChatMP"

    def __init__(self, cfg: dict):
        self.app_id = cfg["app_id"]
        self.app_secret = cfg["app_secret"]
        self.template_id = cfg["template_id"]
        self.open_id = cfg["open_id"]

    async def _get_access_token(self) -> str:
        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            raise Exception(f"获取access_token失败: {data}")

    async def send(self, message: str) -> bool:
        try:
            access_token = await self._get_access_token()
            url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"

            # 模板消息，将内容放入 first 和 remark 字段
            # 用户需根据自己的模板调整 data 字段
            lines = message.split("\n")
            title = lines[0] if lines else "签到通知"
            content = "\n".join(lines[1:]) if len(lines) > 1 else ""

            payload = {
                "touser": self.open_id,
                "template_id": self.template_id,
                "data": {
                    "first": {"value": title, "color": "#173177"},
                    "keyword1": {"value": content[:200], "color": "#173177"},
                    "remark": {"value": content[200:] if len(content) > 200 else "签到完成", "color": "#999999"},
                }
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload)
                result = resp.json()
                if result.get("errcode") == 0:
                    logger.info("[WeChatMP] 推送成功")
                    return True
                else:
                    logger.error(f"[WeChatMP] 推送失败: {result.get('errmsg')}")
                    return False
        except Exception as e:
            logger.error(f"[WeChatMP] 推送异常: {e}")
            return False


# ==================== Server酱 ====================
class ServerChanNotifier(BaseNotifier):
    name = "ServerChan"

    def __init__(self, cfg: dict):
        self.send_key = cfg["send_key"]

    async def send(self, message: str) -> bool:
        url = f"https://sctapi.ftqq.com/{self.send_key}.send"
        lines = message.split("\n")
        title = lines[0] if lines else "森空岛签到通知"

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data={
                "title": title,
                "desp": message,
            })
            result = resp.json()
            if result.get("code") == 0:
                logger.info("[ServerChan] 推送成功")
                return True
            else:
                logger.error(f"[ServerChan] 推送失败: {result.get('message')}")
                return False
