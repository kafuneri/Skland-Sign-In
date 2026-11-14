# notifier.py
import base64
import hashlib
import hmac
import httpx
import logging
import smtplib
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger("notifier")
DEFAULT_HTTP_TIMEOUT = 10.0


class NotifierManager:
    """统一通知管理器，根据配置自动选择可用的推送渠道"""

    def __init__(self, config: dict):
        self.notifiers = []
        notify_cfg = config.get("notify") or {}

        # 兼容老版本的 qmsg_key 配置
        legacy_qmsg_key = config.get("qmsg_key")
        qmsg_cfg = dict(notify_cfg.get("qmsg") or {})
        qmsg_key = qmsg_cfg.get("key") or legacy_qmsg_key

        if qmsg_key:
            qmsg_cfg["key"] = qmsg_key
            self.notifiers.append(QmsgNotifier(qmsg_cfg))

        onebot_cfg = notify_cfg.get("onebot") or {}
        if onebot_cfg.get("url"):
            self.notifiers.append(OneBotNotifier(onebot_cfg))

        email_cfg = dict(notify_cfg.get("email") or {})
        if email_cfg.get("smtp_host"):
            # 强制将密码转为字符串，防止纯数字密码报错
            email_cfg["password"] = str(email_cfg.get("password", ""))
            self.notifiers.append(EmailNotifier(email_cfg))

        wecom_cfg = notify_cfg.get("wecom") or {}
        if wecom_cfg.get("webhook_url"):
            self.notifiers.append(WeComNotifier(wecom_cfg))

        wechat_mp_cfg = notify_cfg.get("wechat_mp") or {}
        if wechat_mp_cfg.get("app_id"):
            self.notifiers.append(WeChatMPNotifier(wechat_mp_cfg))

        serverchan_cfg = notify_cfg.get("serverchan") or {}
        if serverchan_cfg.get("send_key"):
            self.notifiers.append(ServerChanNotifier(serverchan_cfg))

        sc3_cfg = notify_cfg.get("serverchan3") or {}
        if sc3_cfg.get("send_key") or sc3_cfg.get("send_keys"):
            self.notifiers.append(ServerChan3Notifier(sc3_cfg))

        bark_cfg = notify_cfg.get("bark") or {}
        if bark_cfg.get("key") or bark_cfg.get("device_key") or bark_cfg.get("device_keys"):
            self.notifiers.append(BarkNotifier(bark_cfg))
        
        telegram_cfg = notify_cfg.get("telegram") or {}
        if telegram_cfg.get("bot_token") and telegram_cfg.get("chat_id"):
            self.notifiers.append(TelegramNotifier(telegram_cfg))

        dingtalk_cfg = notify_cfg.get("dingtalk") or {}
        if dingtalk_cfg.get("webhook_url"):
            self.notifiers.append(DingTalkNotifier(dingtalk_cfg))
        
        custom_webhook_cfg = notify_cfg.get("custom_webhook") or {}
        if custom_webhook_cfg.get("url"):
            self.notifiers.append(CustomWebhookNotifier(custom_webhook_cfg))    

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
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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
        loop = asyncio.get_running_loop()
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
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.sender, [self.receiver], msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(self.username, self.password)
                    server.sendmail(self.sender, [self.receiver], msg.as_string())

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
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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

            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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


# ==================== Bark ====================
class BarkNotifier(BaseNotifier):
    name = "Bark"

    def __init__(self, cfg: dict):
        self.base_url = (cfg.get("base_url") or "https://api.day.app").rstrip("/")
        self.device_keys = self._parse_device_keys(cfg)
        self.group = cfg.get("group") or "Skland"
        self.sound = cfg.get("sound", "")
        self.icon = cfg.get("icon", "")
        self.url = cfg.get("url", "")
        self.level = cfg.get("level", "")

    @staticmethod
    def _parse_device_keys(cfg: dict) -> list[str]:
        raw_keys = cfg.get("device_keys") or cfg.get("device_key") or cfg.get("key")
        if isinstance(raw_keys, str):
            return [key.strip() for key in raw_keys.split(",") if key.strip()]
        if isinstance(raw_keys, list):
            return [str(key).strip() for key in raw_keys if str(key).strip()]
        return []

    async def send(self, message: str) -> bool:
        if not self.device_keys:
            logger.error("[Bark] 未配置 key 或 device_keys")
            return False

        lines = message.split("\n")
        title = lines[0] if lines else "森空岛签到通知"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else message
        if not body:
            body = message

        payload = {
            "title": title,
            "body": body,
        }
        if len(self.device_keys) == 1:
            payload["device_key"] = self.device_keys[0]
        else:
            payload["device_keys"] = self.device_keys

        for key, value in {
            "group": self.group,
            "sound": self.sound,
            "icon": self.icon,
            "url": self.url,
            "level": self.level,
        }.items():
            if value:
                payload[key] = value

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/push", json=payload)
            result = resp.json()

            if resp.status_code == 200 and result.get("code") in (0, 200, None):
                logger.info("[Bark] 推送成功")
                return True

            logger.error(f"[Bark] 推送失败: {result.get('message') or result}")
            return False


# ==================== Server酱³ ====================
class ServerChan3Notifier(BaseNotifier):
    name = "ServerChan3"

    def __init__(self, cfg: dict):
        # 支持单个 send_key 或多个 send_keys 列表
        raw = cfg.get("send_keys") or cfg.get("send_key", "")
        if isinstance(raw, str):
            self.send_keys = [k.strip() for k in raw.split(",") if k.strip()]
        elif isinstance(raw, list):
            self.send_keys = [str(k).strip() for k in raw if str(k).strip()]
        else:
            self.send_keys = []

    @staticmethod
    def _build_url(send_key: str) -> str:
        import re
        match = re.match(r"sctp(\d+)t", send_key)
        if match:
            uid = match.group(1)
            return f"https://{uid}.push.ft07.com/send/{send_key}.send"
        # 回退到 Turbo 兼容地址（旧版 SCT key）
        return f"https://sctapi.ftqq.com/{send_key}.send"

    async def send(self, message: str) -> bool:
        if not self.send_keys:
            logger.error("[ServerChan3] 未配置 send_key")
            return False

        lines = message.split("\n")
        title = lines[0] if lines else "森空岛签到通知"
        desp = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        payload = {"title": title, "desp": desp}
        headers = {"Content-Type": "application/json;charset=utf-8"}

        all_success = True
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            for key in self.send_keys:
                try:
                    url = self._build_url(key)
                    resp = await client.post(url, json=payload, headers=headers)
                    result = resp.json()
                    if result.get("code") == 0:
                        logger.info(f"[ServerChan3] 推送成功 -> {key[:8]}...")
                    else:
                        logger.error(f"[ServerChan3] 推送失败 -> {key[:8]}...: {result.get('message')}")
                        all_success = False
                except Exception as e:
                    logger.error(f"[ServerChan3] 推送异常 -> {key[:8]}...: {e}")
                    all_success = False
        return all_success

# ==================== Telegram Bot ====================
class TelegramNotifier(BaseNotifier):
    name = "Telegram"

    def __init__(self, cfg: dict):
        self.bot_token = cfg.get("bot_token", "")
        self.chat_id = cfg.get("chat_id", "")
        # 支持自定义反代地址，默认使用官方 API，并清理末尾斜杠
        self.base_url = cfg.get("base_url", "https://api.telegram.org").rstrip("/")

    async def send(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.error("[Telegram] 未配置 bot_token 或 chat_id")
            return False

        url = f"{self.base_url}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message
        }

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(url, json=payload)
                result = resp.json()
                
                if result.get("ok"):
                    logger.info("[Telegram] 推送成功")
                    return True
                else:
                    logger.error(f"[Telegram] 推送失败: {result.get('description')}")
                    return False
            except Exception as e:
                logger.error(f"[Telegram] 推送异常: {e}")
                return False


# ==================== 钉钉群机器人 ====================
class DingTalkNotifier(BaseNotifier):
    name = "DingTalk"

    def __init__(self, cfg: dict):
        self.webhook_url = (cfg.get("webhook_url") or "").strip()
        self.secret = (cfg.get("secret") or "").strip()

    def _build_signed_url(self) -> str:
        """
        钉钉加签规则：
        stringToSign = timestamp + "\\n" + secret
        sign = Base64(HMAC-SHA256(secret, stringToSign))
        最终把 timestamp 和 sign 作为 URL query 参数发送。
        """
        if not self.secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"

        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")

        # 保留 Webhook 原有 access_token，并去掉可能残留的旧 timestamp/sign。
        parts = urlsplit(self.webhook_url)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key not in ("timestamp", "sign")
        ]
        query.extend([
            ("timestamp", timestamp),
            ("sign", sign),
        ])

        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        ))

    async def send(self, message: str) -> bool:
        if not self.webhook_url:
            logger.error("[DingTalk] 未配置 webhook_url")
            return False

        payload = {
            "msgtype": "text",
            "text": {
                "content": message,
            },
        }

        try:
            url = self._build_signed_url()
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
                resp = await client.post(url, json=payload)

            try:
                result = resp.json()
            except Exception:
                logger.error(
                    f"[DingTalk] 推送失败: HTTP {resp.status_code} - 非 JSON 响应: {resp.text}"
                )
                return False

            if resp.status_code == 200 and result.get("errcode") == 0:
                logger.info("[DingTalk] 推送成功")
                return True

            logger.error(
                "[DingTalk] 推送失败: HTTP %s, errcode=%s, errmsg=%s",
                resp.status_code,
                result.get("errcode"),
                result.get("errmsg"),
            )
            return False
        except Exception as e:
            logger.error(f"[DingTalk] 推送异常: {e}")
            return False


# ==================== 自定义 Webhook ====================
class CustomWebhookNotifier(BaseNotifier):
    name = "CustomWebhook"

    def __init__(self, cfg: dict):
        self.url = cfg.get("url", "")
        self.method = (cfg.get("method") or "POST").upper()
        self.headers = cfg.get("headers") or {}
        # 默认回退到一个基础的 json 结构
        body_template = cfg.get("body_template")
        self.body_template = body_template if body_template is not None else {"content": "{{message}}"}

    def _format_payload(self, template, message: str):
        """递归遍历字典或列表，替换占位符"""
        if isinstance(template, dict):
            return {k: self._format_payload(v, message) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._format_payload(v, message) for v in template]
        elif isinstance(template, str):
            return template.replace("{{message}}", message)
        else:
            return template

    async def send(self, message: str) -> bool:
        if not self.url:
            logger.error("[CustomWebhook] 未配置 URL")
            return False

        # 将模板中的 {{message}} 渲染为真实的推送内容
        payload = self._format_payload(self.body_template, message)
        
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            try:
                kwargs = {"headers": self.headers}
                
                # 根据 HTTP 方法自动判定负载挂载位置
                if self.method == "GET":
                    # GET 请求一般挂载在 params (即 URL 的 ?a=1&b=2)
                    kwargs["params"] = payload if isinstance(payload, dict) else {}
                else:
                    # POST/PUT/PATCH 请求
                    if isinstance(payload, str):
                        # 如果模板配置为纯字符串，则发 raw text
                        kwargs["content"] = payload
                    else:
                        # 如果模板配置为字典，则自动序列化为 JSON
                        kwargs["json"] = payload

                # 动态获取对应的请求方法 (client.post / client.get 等)
                request_method = getattr(client, self.method.lower(), client.post)
                resp = await request_method(self.url, **kwargs)
                
                # 兼容 200, 201, 202, 204 等一切 20x 成功状态码
                if resp.status_code in (200, 201, 202, 204):
                    logger.info(f"[CustomWebhook] 推送成功 (HTTP {resp.status_code})")
                    return True
                else:
                    logger.error(f"[CustomWebhook] 推送失败: HTTP {resp.status_code} - 响应: {resp.text}")
                    return False
            except Exception as e:
                logger.error(f"[CustomWebhook] 推送异常: {e}")
                return False
