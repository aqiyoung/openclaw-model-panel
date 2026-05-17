#!/usr/bin/env python3
"""
model-switch.py - OpenClaw 模型切换面板后端 API
"""

import hashlib
import json
import os
import signal
import secrets
import subprocess
import time
import urllib.request
import urllib.error
import concurrent.futures
from http.server import HTTPServer, BaseHTTPRequestHandler

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
ENV_PATH = os.path.expanduser("~/.openclaw/gateway.systemd.env")
GATEWAY_SERVICE = "openclaw-gateway.service"
AUTH_TOKENS = {}  # token -> expiry
_pw = [os.environ.get("PANEL_PASSWORD", "changeme")]  # mutable container for password

def load_env():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key, val)

load_env()
_pw[0] = os.environ.get("PANEL_PASSWORD", "changeme")

def make_token():
    return secrets.token_hex(32)

def check_auth(headers):
    token = headers.get("X-Auth-Token", "")
    if token in AUTH_TOKENS:
        exp = AUTH_TOKENS[token]
        if exp > time.time():
            return True
        del AUTH_TOKENS[token]
    return False

PROVIDERS = {
    "longcat": {"name": "LongCat (美团)", "test_url": "https://api.longcat.chat/openai/v1/models", "env_key": "LONGCAT_API_KEY", "proxy": False},
    "openrouter": {"name": "OpenRouter", "test_url": "https://openrouter.ai/api/v1/models", "env_key": "OPENROUTER_API_KEY", "proxy": True},
    "nvidia": {"name": "NVIDIA NIM", "test_url": "https://integrate.api.nvidia.com/v1/models", "env_key": "NVIDIA_API_KEY", "proxy": True},
    "sensenova": {"name": "SenseNova (商汤)", "test_url": "https://token.sensenova.cn/v1/models", "env_key": "SENSENOVA_API_KEY", "proxy": False},
    "xiaomimimo": {"name": "小米 MiMo", "test_url": "https://token-plan-sgp.xiaomimimo.com/v1/models", "env_key": "XIAOMI_API_KEY", "proxy": True},
    "zai": {"name": "Z.AI (智谱)", "test_url": "https://open.bigmodel.cn/api/paas/v4/models", "env_key": "ZAI_API_KEY", "proxy": False},
}

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except:
        return {}

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def get_provider_configs():
    """从 openclaw.json 读取 provider 的 baseUrl 和 API key 映射"""
    config = load_config()
    providers = config.get("models", {}).get("providers", {})
    result = {}
    for pname, pconf in providers.items():
        pdef = PROVIDERS.get(pname, {})
        result[pname] = {
            "base_url": pconf.get("baseUrl", "").rstrip("/"),
            "env_key": pdef.get("env_key", ""),
            "proxy": pdef.get("proxy", True),
        }
    return result

def chat_with_provider(provider, model_id, message):
    pcfgs = get_provider_configs()
    pcfg = pcfgs.get(provider)
    if not pcfg:
        return {"error": f"未知提供商: {provider}"}
    
    api_key = os.environ.get(pcfg["env_key"], "")
    if not api_key:
        return {"error": f"{provider} 未设置 API Key"}
    
    base_url = pcfg["base_url"]
    url = f"{base_url}/chat/completions"
    
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": message}],
        "max_tokens": 1024,
        "temperature": 0.7,
    }).encode()
    
    # 按需设置代理
    old_proxy = os.environ.pop("HTTPS_PROXY", None)
    old_http_proxy = os.environ.pop("HTTP_PROXY", None)
    if pcfg.get("proxy", True):
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    
    try:
        req = urllib.request.Request(url, data=body)
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        start = time.time()
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
            latency = (time.time() - start) * 1000
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"content": content, "latency_ms": round(latency, 0)}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")[:200]
        return {"error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"error": str(e)[:100]}
    finally:
        if old_proxy is not None:
            os.environ["HTTPS_PROXY"] = old_proxy
        else:
            os.environ.pop("HTTPS_PROXY", None)
        if old_http_proxy is not None:
            os.environ["HTTP_PROXY"] = old_http_proxy
        else:
            os.environ.pop("HTTP_PROXY", None)

def restart_gateway():
    """通过 SIGHUP 强制 gateway 重启（立即生效，约 20s 后 Telegram 恢复）"""
    pid = None
    try:
        r = subprocess.run(["pgrep", "-f", "openclaw.*gateway"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            pid = int(r.stdout.strip().split()[0])
    except:
        pass
    if not pid:
        return False, "找不到 gateway 进程"
    try:
        os.kill(pid, signal.SIGHUP)
        return True, f"信号已发送 (PID {pid})，Gateway 重启中（约 20 秒后生效）..."
    except Exception as e:
        return False, str(e)

def check_provider(pname, pconf):
    api_key = os.environ.get(pconf["env_key"], "")
    if not api_key:
        return {"status": "no_key", "message": "未设置 API Key", "name": pconf["name"]}
    
    # 按需设置代理：国外走代理，国内直连
    old_proxy = os.environ.pop("HTTPS_PROXY", None)
    old_http_proxy = os.environ.pop("HTTP_PROXY", None)
    if pconf.get("proxy", True):
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    
    start = time.time()
    try:
        req = urllib.request.Request(pconf["test_url"])
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=8) as r:
            latency = (time.time() - start) * 1000
            return {"status": "ok", "latency_ms": round(latency, 0), "name": pconf["name"]}
    except urllib.error.HTTPError as e:
        latency = (time.time() - start) * 1000
        return {"status": "error", "latency_ms": round(latency, 0), "http_code": e.code, "name": pconf["name"]}
    except Exception as e:
        return {"status": "timeout", "message": str(e)[:50], "name": pconf["name"]}
    finally:
        # 恢复代理环境变量
        if old_proxy is not None:
            os.environ["HTTPS_PROXY"] = old_proxy
        else:
            os.environ.pop("HTTPS_PROXY", None)
        if old_http_proxy is not None:
            os.environ["HTTP_PROXY"] = old_http_proxy
        else:
            os.environ.pop("HTTP_PROXY", None)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默日志
    
    def is_auth_req(self):
        if check_auth(self.headers):
            return True
        # 也支持 URL 参数传 token
        qs = self.path.split("?")
        if len(qs) > 1:
            params = dict(p.split("=", 1) for p in qs[1].split("&") if "=" in p)
            if params.get("token", "") in AUTH_TOKENS:
                exp = AUTH_TOKENS[params["token"]]
                if exp > time.time():
                    return True
                del AUTH_TOKENS[params["token"]]
        return False

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        
        if path == "/api/login" or path.startswith("/api/login"):
            pass  # skip auth
        elif path.startswith("/api/") and not self.is_auth_req():
            self.send_json({"error": "未授权，请先登录"}, 401)
            return
        
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.get_panel_html().encode())
        elif path == "/api/status":
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                futures = {name: ex.submit(check_provider, name, cfg) for name, cfg in PROVIDERS.items()}
                status = {name: f.result(timeout=10) for name, f in futures.items()}
            self.send_json(status)
        elif path == "/api/config":
            config = load_config()
            result = {
                "default_model": config.get("agents", {}).get("defaults", {}).get("model", ""),
                "providers": list(config.get("models", {}).get("providers", {}).keys()),
                "agents": {a.get("id", "unknown"): a.get("model", {}) for a in config.get("agents", {}).get("list", [])},
            }
            self.send_json(result)
        elif path == "/api/models":
            config = load_config()
            providers = config.get("models", {}).get("providers", {})
            result = {}
            for pname, pconf in providers.items():
                models = pconf.get("models", [])
                result[pname] = {
                    "name": PROVIDERS.get(pname, {}).get("name", pname),
                    "base_url": pconf.get("baseUrl", ""),
                    "model_count": len(models),
                    "models": [{"id": m.get("id"), "name": m.get("name")} for m in models],
                }
            self.send_json(result)
        else:
            self.send_error(404)
    
    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""
        
        if path == "/api/login":
            try:
                data = json.loads(body)
                pw = data.get("password", "")
                if pw == _pw[0]:
                    token = make_token()
                    AUTH_TOKENS[token] = time.time() + 86400  # 24h
                    self.send_json({"ok": True, "token": token})
                else:
                    self.send_json({"error": "密码错误"}, 403)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return
        
        if not self.is_auth_req():
            self.send_json({"error": "未授权，请先登录"}, 401)
            return
        
        if path == "/api/change-password":
            try:
                data = json.loads(body)
                old_pw = data.get("old_password", "")
                new_pw = data.get("new_password", "")
                if not new_pw or len(new_pw) < 4:
                    self.send_json({"error": "新密码至少 4 位"}, 400)
                    return
                if old_pw != _pw[0]:
                    self.send_json({"error": "原密码错误"}, 403)
                    return
                _pw[0] = new_pw
                # 写入 env 文件
                try:
                    lines = []
                    found = False
                    with open(ENV_PATH) as f:
                        for line in f:
                            if line.startswith("PANEL_PASSWORD="):
                                lines.append(f"PANEL_PASSWORD={new_pw}\n")
                                found = True
                            else:
                                lines.append(line)
                    if not found:
                        lines.append(f"PANEL_PASSWORD={new_pw}\n")
                    with open(ENV_PATH, "w") as f:
                        f.writelines(lines)
                except Exception:
                    pass
                # 重新加载 gateway 的环境变量文件
                subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
                self.send_json({"ok": True, "message": "密码已修改"})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return
        
        if path == "/api/switch":
            try:
                data = json.loads(body)
                provider = data.get("provider", "")
                model_id = data.get("model_id", "")
                if not provider or not model_id:
                    self.send_json({"error": "需要 provider 和 model_id"}, 400)
                    return
                # 1. 更新 config 默认模型
                config = load_config()
                old_model = config.get("agents", {}).get("defaults", {}).get("model", "")
                config.setdefault("agents", {}).setdefault("defaults", {})["model"] = model_id
                save_config(config)
                # 2. 更新所有面向用户的会话的 modelOverride（跳过 cron/subagent 等内部会话）
                try:
                    sessions_path = os.path.expanduser("~/.openclaw/agents/main/sessions/sessions.json")
                    if os.path.exists(sessions_path):
                        with open(sessions_path) as f:
                            sessions = json.load(f)
                        changed = False
                        for key in list(sessions.keys()):
                            if ":cron:" in key or ":subagent:" in key or ":dreaming-" in key:
                                continue
                            sessions[key]["model"] = model_id
                            sessions[key]["modelOverride"] = model_id
                            sessions[key]["modelProvider"] = provider
                            sessions[key]["providerOverride"] = provider
                            if "modelOverrideSource" in sessions[key]:
                                del sessions[key]["modelOverrideSource"]
                            if "providerModel" in sessions[key]:
                                sessions[key]["providerModel"] = model_id
                            changed = True
                        if changed:
                            with open(sessions_path, "w") as f:
                                json.dump(sessions, f, ensure_ascii=False)
                except Exception:
                    pass
                # 3. 重启 gateway
                restart_ok, restart_msg = restart_gateway()
                msg = f"已切换: {old_model} → {model_id}，{restart_msg}" if restart_ok else f"配置已保存但重启失败: {restart_msg}"
                self.send_json({"ok": restart_ok, "old_model": old_model, "new_model": model_id, "message": msg})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        elif path == "/api/chat":
            try:
                data = json.loads(body)
                provider = data.get("provider", "")
                model_id = data.get("model_id", "")
                message = data.get("message", "")
                if not provider or not model_id or not message:
                    self.send_json({"error": "需要 provider, model_id 和 message"}, 400)
                    return
                result = chat_with_provider(provider, model_id, message)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        elif path == "/api/reload":
            try:
                ok, msg = restart_gateway()
                self.send_json({"ok": ok, "message": msg})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def get_panel_html(self):
        return open(os.path.join(os.path.dirname(__file__), "model-switch.html")).read()

if __name__ == "__main__":
    port = 18790
    server = HTTPServer((("0.0.0.0", port)), Handler)
    print(f"Model Switch Panel: http://127.0.0.1:{port}")
    server.serve_forever()
