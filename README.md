

## 环境变量（完整参考）

| 变量 | OpenClaw 默认值 | Hermes 建议值 | 说明 |
|---|---|---|---|
| `PANEL_PASSWORD` | `changeme` | `changeme` | 面板登录口令 |
| `PANEL_CONFIG` | `~/.openclaw/openclaw.json` | `~/.hermes/config.yaml` | 配置文件路径 |
| `PANEL_CONFIG_FORMAT` | `auto` | `auto` | json / yaml / auto |
| `PANEL_SESSIONS` | `~/.openclaw/agents/main/sessions/sessions.json` | —（Hermes 无会话文件） | 会话文件路径（仅 OpenClaw） |
| `PANEL_SERVICE` | `openclaw-gateway.service` | `hermes-gateway.service` | systemd 服务名 |
| `PANEL_RESTART_CMD` | — | — | 自定义重启命令（优先于 systemd） |
| `PANEL_PORT` | `18790` | `18790` | 监听端口 |
| `PANEL_ENV_PATH` | `~/.openclaw/gateway.systemd.env` | `~/.hermes/.env` | 面板读取的环境变量文件 |
| `PANEL_MODEL_FIELD` | 自动检测 | `model.default` | 配置文件中模型字段路径 |
| `PANEL_PROVIDERS_PATH` | 自动检测（`models.providers`） | —（Hermes 从 ProviderProfile 检测） | Provider 定义路径（仅 OpenClaw） |
| `PANEL_FRAMEWORK` | `auto` | `hermes` | openclaw / hermes / auto |

