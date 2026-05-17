# OpenClaw Model Switch Panel

OpenClaw 模型切换面板。在网页上查看所有模型提供商的连通性和延迟，一键切换模型——**Telegram、飞书、Discord、微信等所有平台同时生效**。

## 预览

- 提供商状态实时检测（延迟、可用性）
- 模型分组展示（按提供商）
- 一键切换模型 → 自动更新配置 + 所有平台会话 + 热重载 Gateway
- 直接对话测试（`/api/chat`，跳过 Gateway，直连 API）
- 密码保护 + 修改口令

## 前置条件

- OpenClaw Gateway（2026.5+）
- systemd（user mode）
- Python 3.10+
- nginx（可选，如果需要域名访问）

## 安装

```bash
# 1. 下载文件到 OpenClaw 脚本目录
cp model-switch.py model-switch.html ~/.openclaw/workspace/scripts/

# 2. 配置环境变量
cat >> ~/.openclaw/gateway.systemd.env << 'EOF'
PANEL_PASSWORD=your_password
EOF

# 3. 安装 systemd 服务
mkdir -p ~/.config/systemd/user/
cp model-switch.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openclaw-model-switch.service

# 4. 验证
systemctl --user status openclaw-model-switch.service
curl http://127.0.0.1:18790/
```

## nginx 反代（可选）

```nginx
server {
    listen 80;
    server_name panel.example.com;

    location / {
        proxy_pass http://127.0.0.1:18790;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## API

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/status` | GET | 查询所有提供商连通性 |
| `/api/config` | GET | 获取当前配置 |
| `/api/models` | GET | 获取所有可用模型 |
| `/api/switch` | POST | 切换模型（所有平台同步生效） |
| `/api/chat` | POST | 直接对话测试 |
| `/api/reload` | POST | 重载 Gateway |
| `/api/login` | POST | 登录获取 Token |
| `/api/change-password` | POST | 修改口令 |

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `PANEL_PASSWORD` | 是 | 面板登录口令 |
| `LONGCAT_API_KEY` | 否 | 美团 LongCat |
| `OPENROUTER_API_KEY` | 否 | OpenRouter |
| `NVIDIA_API_KEY` | 否 | NVIDIA NIM |
| `SENSENOVA_API_KEY` | 否 | 商汤 SenseNova |
| `XIAOMI_API_KEY` | 否 | 小米 MiMo |
| `ZAI_API_KEY` | 否 | 智谱 Z.AI |
| `HTTP_PROXY` | 否 | 代理 |
| `HTTPS_PROXY` | 否 | 代理 |
| `NO_PROXY` | 否 | 直连域名 |

## 工作原理

1. **面板**读取 OpenClaw 配置文件（`openclaw.json`）中的 `agents.defaults.model`
2. 切换时：**同时更新** config + 所有平台的会话（`sessions.json`）+ 发送 `SIGHUP` 给 Gateway
3. 这样无论你通过哪个平台（Telegram / 飞书 / Discord / 微信 / WebChat）与 Bot 对话，都立即使用新模型
