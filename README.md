# Skland-Sign-In

森空岛自动签到脚本，用于实现森空岛平台下《明日方舟》与《终末地》的每日自动签到。  
支持多账号管理及多种消息推送渠道。

## 环境要求

* Python 3.8 或更高版本
* 或 Docker 环境
> 如没有NAS或服务器环境，可以使用`GitHub Actions`签到，但海外网络存在触发森空岛风控的风险（目前未发现），另外使用 GitHub Actions 运行签到脚本存在违反 GitHub ToS 的风险，请谨慎使用并自行承担后果。

## 配置指南

在使用前，请将目录下的 `config.example.yaml` 文件另存为 `config.yaml` 进行配置。

```bash
# 拉取代码
git clone https://github.com/kafuneri/Skland-Sign-In.git && cd Skland-Sign-In
cp config.example.yaml config.yaml

```

### 1. 填写用户信息

在 `users` 列表下填写账号昵称和 Token。

**如何获取 Token：**

1. 登录 [森空岛官网](https://www.skland.com/)。
2. 登录成功后，访问此链接：[https://web-api.skland.com/account/info/hg](https://web-api.skland.com/account/info/hg)
3. 页面将返回一段 JSON 数据。请复制 `content` 字段中的长字符串。
* 数据示例：`{"code":0,"data":{"content":"请复制这一长串字符"}}`

### 2. 配置消息推送 (可选)

本项目支持多种推送渠道，请在 `config.yaml` 的 `notify` 节点下配置：

* **Qmsg 酱**：通过 QQ 发送通知。
* **OneBot V11**：支持 NapCat、go-cqhttp 等协议，可推送至私聊或群聊。
* **电子邮件 (SMTP)**：支持 QQ、网易等主流邮箱推送。
* **企业微信**：通过群机器人 Webhook 推送。
* **微信服务号**：通过公众号模板消息推送。
* **Server 酱 (Turbo版/Server酱³ )**：通过微信/手机客户端推送。
* **Bark**：通过 Bark App 推送到 iOS 设备，支持官方服务和自建 Bark Server。

---

## 部署方法

### 方案一：Docker 部署 (推荐)

本项目内置了 Cron 定时任务（默认每天凌晨 01:00 运行），适合 NAS 或服务器环境。

#### 使用 Docker Compose

在项目目录下配置 `docker-compose.yml`（已内置，一般无需修改）并运行：

```bash
docker compose up -d

```

#### 使用 Docker Run

```bash
docker run -d \
  --name skland-sign \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -e TZ=Asia/Shanghai \
  kafuneri/skland-sign-in:latest

```


### 方案二：GitHub Actions 自动运行

项目已内置 GitHub Actions 工作流，默认每天北京时间 01:00 自动运行一次，也可以在 GitHub 页面手动触发。

1. 点击页面右上角的 Fork 按钮，将本项目推送到你自己的 GitHub 仓库。
2. 在仓库页面进入 `Settings` -> `Secrets and variables` -> `Actions`。
3. 新增 Repository secret，名称填写 `CONFIG_YAML`，内容填写你完整的 `config.yaml` 文件内容。
4. 进入 `Actions` -> `Skland Sign In`，点击 `Run workflow` 可手动测试运行。

> 注意：GitHub Actions 的 Cron 表达式使用 UTC 时间。默认工作流配置 `0 17 * * *` 对应北京时间次日 01:00。如需修改时间，请编辑 `.github/workflows/sign-in.yml` 中的 `schedule.cron`。


 
### 方案三：源码运行

1. 克隆本项目后安装依赖：
```bash
pip install -r requirements.txt

```


2. 执行签到脚本：
```bash
python3 main.py

```
脚本运行后会依次检查每个配置账号的签到状态：

* 若未签到，则执行签到并获取奖励内容。
* 若已签到，则跳过。
* 运行结束后会输出简报，如果配置了相关通知渠道（如 Qmsg、Bark、邮件等），则会发送对应的推送通知。


---

## 定时任务配置

若使用 Docker 部署，可以通过修改 `config.yaml` 中的 `cron` 字段来自定义执行时间（Cron 表达式）。  
若使用 GitHub Actions 部署，请修改 `.github/workflows/sign-in.yml` 中的 `schedule.cron`。<br>
若源码运行，建议配合计划任务实现每日自动运行，网上教程很多，此处不赘述。

## 运行截图  
<img width="366" height="295" alt="image" src="https://github.com/user-attachments/assets/55ee4bbc-3f3a-4e63-8746-3dcbc059ff90" />

## 感谢以下项目

* 本项目的核心 API 交互逻辑（`skland_api.py`）提取自 AstrBot 的开源插件 [astrbot_plugin_skland](https://github.com/Azincc/astrbot_plugin_skland)