# Model Switch Panel

通用模型切换面板。在网页上查看所有模型提供商的连通性和延迟，一键切换模型——**所有平台同时生效**（Telegram、飞书、Discord、微信等）。

支持 **OpenClaw**、**Hermes** 等任意 Bot 框架，通过环境变量配置路径和行为。

## 功能

- 提供商状态实时检测（延迟、可用性）
- 模型分组展示（按提供商）
- 一键切换模型 → 自动更新配置 + 同步会话 + 热重载服务
- 直接对话测试（跳过 Bot，直连 API）
- 密码保护 + 修改口令

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PANEL_PASSWORD` | `changeme` | 面板登录口令 |
| `PANEL_CONFIG` | `~/.openclaw/openclaw.json` | 配置文件路径 |
| `PANEL_SESSIONS` | `~/.openclaw/agents/main/sessions/sessions.json` | 会话文件路径（可选） |
| `PANEL_SERVICE` | `openclaw-gateway.service` | systemd 服务名 |
| `PANEL_PORT` | `18790` | 监听端口 |
| `PANEL_PROVIDERS_PATH` | `models.providers` | JSON 中 provider 所在路径 |
| `PANEL_DEFAULT_MODEL_PATH` | `agents.defaults.model` | JSON 中默认模型路径 |
| `PANEL_ENV_PATH` | `~/.openclaw/gateway.systemd.env` | 环境变量文件路径 |
| `HTTP_PROXY` | — | HTTP 代理 |
| `HTTPS_PROXY` | — | HTTPS 代理 |
| `NO_PROXY` | — | 不走代理的域名 |

## 安装

```bash
# 1. 下载文件
cp model-switch.py model-switch.html /path/to/your/script/dir/

# 2. 设置面板口令（首次部署）
# 把下面的 CHANGE_MY_PASSWORD 换成你自己的密码
echo "PANEL_PASSWORD=CHANGE_MY_PASSWORD" >> /path/to/your/env/file

# 3. 安装系统服务
cp model-switch.service ~/.config/systemd/user/
# 修改 service 文件中的 ExecStart 路径
systemctl --user daemon-reload
systemctl --user enable --now model-switch.service

# 4. 验证
curl http://127.0.0.1:18790/
```

> 提供商和 API Key 通过配置文件自动读取，支持 `${ENV_VAR}` 和明文两种方式。

## nginx 反代（可选）

```nginx
server {
    listen 80;
    server_name panel.example.com;
    location / {
        proxy_pass http://127.0.0.1:18790;
    }
}
```

## API

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/status` | GET | 查询所有提供商连通性 |
| `/api/config` | GET | 获取当前配置 |
| `/api/models` | GET | 获取所有可用模型 |
| `/api/switch` | POST | 切换模型（所有平台同步） |
| `/api/chat` | POST | 直连 API 对话测试 |
| `/api/reload` | POST | 重载服务进程 |
| `/api/login` | POST | 登录获取 Token |
| `/api/change-password` | POST | 修改口令 |

## Hermes 配置示例

```bash
PANEL_CONFIG=~/.hermes/config.json
PANEL_SESSIONS=~/.hermes/sessions.json
PANEL_SERVICE=hermes.service
PANEL_PROVIDERS_PATH=providers
PANEL_DEFAULT_MODEL_PATH=defaults.model
PANEL_ENV_PATH=~/.hermes/env
```
