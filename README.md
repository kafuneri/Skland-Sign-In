# Skland-Sign-In

森空岛自动签到脚本，用于实现森空岛平台下《明日方舟》与《终末地》的每日自动签到。  
支持多账号管理及 Qmsg酱 消息推送。

## 环境要求

* Python 3.8 或更高版本

## 安装步骤

1. 克隆或下载本项目到本地。
```bash
git clone https://github.com/kafuneri/Skland-Sign-In.git && cd Skland-Sign-In
```
2. 在项目根目录下，安装所需依赖：

```bash
pip install -r requirements.txt

```

## 配置指南

在使用前，请将目录下的 `config.example.yaml` 文件另存为`config.yaml`进行配置。
```bash
cp config.example.yaml config.yaml

```
### 1. 填写用户信息

在 `users` 列表下填写账号昵称和 Token。

**如何获取 Token：**

1. 登录 [森空岛官网](https://www.skland.com/)。
2. 登录成功后，访问此链接：[https://web-api.skland.com/account/info/hg](https://web-api.skland.com/account/info/hg)
3. 页面将返回一段 JSON 数据。请复制 `content` 字段中的长字符串。
* 数据示例：`{"code":0,"data":{"content":"请复制这一长串字符"}}`


4. 将复制的字符串填入 `config.yaml` 的 `token` 字段。

> 注意：Token 等同于账号凭证，请勿泄露给他人。

### 2. 配置消息推送 (可选)

如果需要签到结果通知，本脚本支持 Qmsg酱 推送。

1. 注册并登录 [Qmsg酱](https://qmsg.zendee.cn/)。
2. 在管理台获取你的 KEY。
3. 将 KEY 填入 `config.yaml` 的 `qmsg_key` 字段。如果不使用推送，请留空。

### 配置文件示例

```yaml
# 日志等级: debug (显示详细信息) 或 info (仅显示结果)
log_level: "info"

# Qmsg 推送 Key (选填，留空则不推送)
qmsg_key: "你的Key"

users:
  - nickname: "账号A"
    token: "从上述步骤获取的Token字符串"
    
  - nickname: "账号B"
    token: "另一个Token"

```

## 运行方法

在终端中执行以下命令启动脚本：

```bash
python3 main.py

```

脚本运行后会依次检查每个配置账号的签到状态：

* 若未签到，则执行签到并获取奖励内容。
* 若已签到，则跳过。
* 运行结束后会输出简报，如果配置了 Qmsg，会发送推送到 QQ。
* 建议配合计划任务实现每日自动运行，网上教程很多，此处不赘述。

  
