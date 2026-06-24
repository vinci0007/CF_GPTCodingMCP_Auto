from __future__ import annotations

import os
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
import urllib.error
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
RUNTIME = ROOT / ".runtime"
LOGS = RUNTIME / "logs"
STATE = RUNTIME / "state"
BIN = RUNTIME / "bin"
CLOUDFLARED_RUNTIME = RUNTIME / "cloudflared"
SNIPPET_FILE = RUNTIME / "codex-mcp-snippet.toml"
PROXY_FILE = RUNTIME / "proxy.env"
PROJECTS_FILE = RUNTIME / "projects.json"
PID_FILE = STATE / "coding-tools-mcp.pid"
TUNNEL_PID_FILE = STATE / "cloudflared.pid"
TUNNEL_URL_FILE = STATE / "cloudflared-url.txt"
TUNNEL_LOG_FILE = STATE / "cloudflared-log.txt"
NAMED_TUNNEL_URL_FILE = STATE / "named-tunnel-url.txt"
NAMED_TUNNEL_TOKEN_FILE = STATE / "named-tunnel-token.txt"
OAUTH_PASSWORD_FILE = STATE / "oauth-password.txt"
OAUTH_CLIENT_ID_FILE = STATE / "oauth-client-id.txt"
OAUTH_CLIENT_SECRET_FILE = STATE / "oauth-client-secret.txt"
SESSION_FILE = RUNTIME / "sessions.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
DEFAULT_WORKSPACE = ROOT
DEFAULT_TOOL_PROFILE = "read-only"
DEFAULT_PERMISSION_MODE = "safe"
CHATGPT_INSTRUCTIONS = """默认使用 Coding Tools MCP 读取、搜索和修改当前项目文件。需要修改代码时，不要只输出 diff；优先调用 MCP 的 apply_patch。对长函数或重复结构，先读取目标文件相关片段，使用更长且唯一的上下文锚点。如果 apply_patch 因上下文不匹配失败，重新读取文件后用更精确上下文重试；只有工具不可用时才给用户手动 diff。"""


@dataclass
class RunningProcess:
    pid: int


@dataclass
class CodexConfigCandidate:
    path: Path
    exists: bool


@dataclass
class ProjectEntry:
    name: str
    path: str
    port: int = DEFAULT_PORT
    tool_profile: str = "read-only"
    permission_mode: str = "safe"
    allow_network: bool = False


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause() -> None:
    input("\nPress Enter to continue...")


def ensure_dirs() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    BIN.mkdir(parents=True, exist_ok=True)
    CLOUDFLARED_RUNTIME.mkdir(parents=True, exist_ok=True)


def project_name_from_path(path: Path) -> str:
    return path.name or str(path)


def load_projects_data() -> dict:
    ensure_dirs()
    if not PROJECTS_FILE.exists():
        return {
            "current": str(DEFAULT_WORKSPACE),
            "projects": [
                {
                    "name": project_name_from_path(DEFAULT_WORKSPACE),
                    "path": str(DEFAULT_WORKSPACE),
                    "port": DEFAULT_PORT,
                    "tool_profile": DEFAULT_TOOL_PROFILE,
                    "permission_mode": DEFAULT_PERMISSION_MODE,
                    "allow_network": False,
                }
            ],
        }
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        if "projects" not in data or not isinstance(data["projects"], list):
            raise ValueError("Invalid projects file.")
        return data
    except Exception:
        return {"current": str(DEFAULT_WORKSPACE), "projects": []}


def save_projects_data(data: dict) -> None:
    ensure_dirs()
    PROJECTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_projects() -> list[ProjectEntry]:
    data = load_projects_data()
    entries: list[ProjectEntry] = []
    seen: set[str] = set()
    for raw in data.get("projects", []):
        path = str(raw.get("path", "")).strip()
        if not path or path in seen:
            continue
        seen.add(path)
        entries.append(
            ProjectEntry(
                name=str(raw.get("name") or project_name_from_path(Path(path))),
                path=path,
                port=int(raw.get("port") or DEFAULT_PORT),
                tool_profile=str(raw.get("tool_profile") or DEFAULT_TOOL_PROFILE),
                permission_mode=str(raw.get("permission_mode") or DEFAULT_PERMISSION_MODE),
                allow_network=bool(raw.get("allow_network", False)),
            )
        )
    if not entries:
        entries.append(ProjectEntry(name=project_name_from_path(DEFAULT_WORKSPACE), path=str(DEFAULT_WORKSPACE)))
    return entries


def current_project_path() -> str:
    data = load_projects_data()
    current = str(data.get("current") or "").strip()
    if current:
        return current
    projects = list_projects()
    return projects[0].path


def upsert_project(entry: ProjectEntry, make_current: bool = True) -> None:
    data = load_projects_data()
    projects = [item for item in data.get("projects", []) if str(item.get("path")) != entry.path]
    projects.insert(
        0,
        {
            "name": entry.name,
            "path": entry.path,
            "port": entry.port,
            "tool_profile": entry.tool_profile,
            "permission_mode": entry.permission_mode,
            "allow_network": entry.allow_network,
        },
    )
    data["projects"] = projects
    if make_current:
        data["current"] = entry.path
    save_projects_data(data)


def remove_project(path: str) -> None:
    data = load_projects_data()
    data["projects"] = [item for item in data.get("projects", []) if str(item.get("path")) != path]
    if data.get("current") == path:
        data["current"] = data["projects"][0]["path"] if data["projects"] else str(DEFAULT_WORKSPACE)
    save_projects_data(data)


def title() -> None:
    clear()
    print("Coding Tools MCP Launcher")
    print(f"Root: {ROOT}")
    print(f"Venv: {VENV}")
    print(f"Runtime: {RUNTIME}")
    print(f"Workspace: {DEFAULT_WORKSPACE}")
    print()


def which(command: str) -> str | None:
    return shutil.which(command)


def prompt(default: str, message: str) -> str:
    value = input(f"{message} [{default}]: ").strip()
    return value or default


def prompt_bool(default: bool, message: str) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{message} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1"}


def prompt_choice(default: str, message: str, options: Iterable[str]) -> str:
    value = input(f"{message} [{default}]: ").strip()
    value = value or default
    if value not in options:
        print(f"Invalid choice. Using {default}.")
        return default
    return value


def venv_python() -> Path:
    return VENV / "Scripts" / "python.exe" if os.name == "nt" else VENV / "bin" / "python"


def venv_mcp() -> Path:
    return VENV / "Scripts" / "coding-tools-mcp.exe" if os.name == "nt" else VENV / "bin" / "coding-tools-mcp"


def cloudflared_command() -> str | None:
    local_exe = BIN / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
    if local_exe.exists():
        return str(local_exe)
    return which("cloudflared")


def local_cloudflared_path() -> Path:
    return BIN / ("cloudflared.exe" if os.name == "nt" else "cloudflared")


def install_cloudflared_local() -> Path:
    ensure_dirs()
    target = local_cloudflared_path()
    if target.exists():
        return target

    if os.name != "nt":
        raise RuntimeError("Auto-install cloudflared is currently implemented for Windows only.")

    download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    temp_path = BIN / "cloudflared-download.exe"
    request = urllib.request.Request(download_url, headers={"User-Agent": "coding-tools-launcher"})
    proxy_settings = read_proxy_settings()
    opener = None
    if proxy_settings:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(
                {
                    "http": proxy_settings.get("HTTP_PROXY"),
                    "https": proxy_settings.get("HTTPS_PROXY"),
                }
            )
        )
    if opener:
        with opener.open(request, timeout=120) as response, temp_path.open("wb") as output:
            shutil.copyfileobj(response, output)
    else:
        with urllib.request.urlopen(request, timeout=120) as response, temp_path.open("wb") as output:
            shutil.copyfileobj(response, output)
    temp_path.replace(target)
    return target


def is_venv_ready() -> bool:
    return venv_python().exists()


def load_pid() -> RunningProcess | None:
    return load_pid_from(PID_FILE)


def load_tunnel_pid() -> RunningProcess | None:
    return load_pid_from(TUNNEL_PID_FILE)


def load_pid_from(path: Path) -> RunningProcess | None:
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        return RunningProcess(pid=pid)
    except Exception:
        return None


def process_alive(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        return str(pid) in result.stdout
    return Path(f"/proc/{pid}").exists()


def read_proxy_settings() -> dict[str, str]:
    if not PROXY_FILE.exists():
        return {}
    settings: dict[str, str] = {}
    for raw_line in PROXY_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        settings[key.strip()] = value.strip().strip('"')
    return settings


def save_proxy_settings(proxy_url: str) -> None:
    ensure_dirs()
    content = "\n".join(
        [
            f'HTTP_PROXY="{proxy_url}"',
            f'HTTPS_PROXY="{proxy_url}"',
            f'ALL_PROXY="{proxy_url}"',
        ]
    )
    PROXY_FILE.write_text(content + "\n", encoding="utf-8")


def proxy_enabled() -> bool:
    return bool(read_proxy_settings())


def normalize_proxy_url(protocol: str, host: str, port: str) -> str:
    protocol = protocol.strip().lower().removesuffix("://")
    host = host.strip()
    port = port.strip()
    if not protocol:
        protocol = "http"
    if not host:
        host = "127.0.0.1"
    if not port:
        port = "20100"
    return f"{protocol}://{host}:{port}"


def clear_proxy_settings() -> None:
    PROXY_FILE.unlink(missing_ok=True)


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(read_proxy_settings())
    return env


def current_proxy_summary() -> str:
    settings = read_proxy_settings()
    if settings:
        return settings.get("HTTP_PROXY", "configured")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        value = os.environ.get(key)
        if value:
            return value
    return "none"


def wait_for_port(host: str, port: int, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def wait_for_port_closed(host: str, port: int, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                time.sleep(0.25)
        except OSError:
            return True
    return False


def can_bind_port(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


def choose_bindable_port(preferred_port: int) -> int:
    if can_bind_port(DEFAULT_HOST, preferred_port):
        return preferred_port
    for port in (8010, 18080, 18765, 28765, 38765, 49152):
        if can_bind_port(DEFAULT_HOST, port):
            return port
    raise RuntimeError("No bindable localhost port found.")


def codex_config_candidates() -> list[CodexConfigCandidate]:
    home = Path.home()
    candidates: list[Path] = [ROOT / ".codex" / "config.toml", home / ".codex" / "config.toml"]

    code_home = os.environ.get("CODEX_HOME")
    if code_home:
        candidates.append(Path(code_home) / "config.toml")

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        candidates.append(Path(xdg_config_home) / "codex" / "config.toml")

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Codex" / "config.toml")

    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        candidates.append(Path(localappdata) / "Codex" / "config.toml")

    seen: set[Path] = set()
    result: list[CodexConfigCandidate] = []
    for candidate in candidates:
        resolved = candidate.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(CodexConfigCandidate(path=resolved, exists=resolved.exists()))
    return result


def display_codex_configs() -> None:
    title()
    print("Codex config candidates")
    for candidate in codex_config_candidates():
        mark = "*" if candidate.exists else " "
        print(f"{mark} {candidate.path}")
    print()
    print("* = existing file")
    pause()


def render_snippet(port: int) -> str:
    return f'''[mcp_servers.coding_tools]\nurl = "http://{DEFAULT_HOST}:{port}/mcp"\n'''


def latest_tunnel_url() -> str | None:
    running = load_tunnel_pid()
    if not running or not process_alive(running.pid):
        return None
    active_log_files: list[Path] = []
    has_active_log = False
    if TUNNEL_LOG_FILE.exists():
        active_log = Path(TUNNEL_LOG_FILE.read_text(encoding="utf-8").strip())
        if active_log.exists():
            active_log_files.append(active_log)
            has_active_log = True
    if not active_log_files:
        active_log_files = sorted(LOGS.glob("cloudflared-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    for log_file in active_log_files:
        matches = re.findall(
            r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com",
            log_file.read_text(encoding="utf-8", errors="ignore"),
        )
        if matches:
            return matches[-1]
    if has_active_log:
        return None
    if TUNNEL_URL_FILE.exists():
        value = TUNNEL_URL_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def wait_for_tunnel_url(timeout_seconds: float = 30.0) -> str | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        url = latest_tunnel_url()
        if url:
            TUNNEL_URL_FILE.write_text(url, encoding="utf-8")
            return url
        time.sleep(0.5)
    return None


def latest_named_tunnel_url() -> str | None:
    if NAMED_TUNNEL_URL_FILE.exists():
        value = NAMED_TUNNEL_URL_FILE.read_text(encoding="utf-8-sig").strip().lstrip("\ufeff").rstrip("/")
        if value:
            return value
    return None


def latest_named_tunnel_token() -> str | None:
    if NAMED_TUNNEL_TOKEN_FILE.exists():
        value = NAMED_TUNNEL_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def named_tunnel_config_path() -> Path:
    return CLOUDFLARED_RUNTIME / "config.yml"


def save_named_tunnel_settings(public_url: str, token: str) -> None:
    ensure_dirs()
    public_url = public_url.strip().lstrip("\ufeff").rstrip("/")
    token = token.strip()
    if public_url:
        NAMED_TUNNEL_URL_FILE.write_text(public_url, encoding="utf-8")
    if token:
        NAMED_TUNNEL_TOKEN_FILE.write_text(token, encoding="utf-8")


def get_or_create_oauth_password(reset: bool = False) -> str:
    ensure_dirs()
    if not reset and OAUTH_PASSWORD_FILE.exists():
        value = OAUTH_PASSWORD_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    password = secrets.token_urlsafe(32)
    OAUTH_PASSWORD_FILE.write_text(password, encoding="utf-8")
    return password


def get_or_create_oauth_client_id(reset: bool = False) -> str:
    ensure_dirs()
    if not reset and OAUTH_CLIENT_ID_FILE.exists():
        value = OAUTH_CLIENT_ID_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    client_id = "coding-tools-mcp"
    OAUTH_CLIENT_ID_FILE.write_text(client_id, encoding="utf-8")
    return client_id


def get_or_create_oauth_client_secret(reset: bool = False) -> str:
    ensure_dirs()
    if not reset and OAUTH_CLIENT_SECRET_FILE.exists():
        value = OAUTH_CLIENT_SECRET_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    client_secret = secrets.token_urlsafe(32)
    OAUTH_CLIENT_SECRET_FILE.write_text(client_secret, encoding="utf-8")
    return client_secret


def latest_oauth_password() -> str | None:
    if OAUTH_PASSWORD_FILE.exists():
        value = OAUTH_PASSWORD_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    for log_file in sorted(LOGS.glob("chatgpt-web-mcp-*.log"), key=lambda path: path.stat().st_mtime, reverse=True):
        match = re.search(r"OAuth authorize password:\s*(\S+)", log_file.read_text(encoding="utf-8", errors="ignore"))
        if match:
            return match.group(1)
    return None


def latest_oauth_client_id() -> str | None:
    if OAUTH_CLIENT_ID_FILE.exists():
        value = OAUTH_CLIENT_ID_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def latest_oauth_client_secret() -> str | None:
    if OAUTH_CLIENT_SECRET_FILE.exists():
        value = OAUTH_CLIENT_SECRET_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def start_chatgpt_web_server(
    workspace_path: Path,
    port: int,
    server_url: str | None = None,
    tool_profile: str = "full",
    permission_mode: str = "trusted",
    allow_network: bool = True,
    strict_port: bool = False,
) -> subprocess.Popen:
    ensure_dirs()
    if not venv_mcp().exists():
        raise RuntimeError("coding-tools-mcp is not installed in .venv.")

    if strict_port and not can_bind_port(DEFAULT_HOST, port):
        raise RuntimeError(f"Port {port} is still in use; stop the old MCP server and retry.")
    port = port if strict_port else choose_bindable_port(port)
    args = [
        str(venv_mcp()),
        "--workspace",
        str(workspace_path),
        "--host",
        DEFAULT_HOST,
        "--port",
        str(port),
        "--oauth-mode",
        "--tool-profile",
        tool_profile,
        "--permission-mode",
        permission_mode,
    ]
    if allow_network:
        args.append("--allow-network")

    env = build_env()
    env["CODING_TOOLS_MCP_OAUTH_PASSWORD"] = get_or_create_oauth_password()
    env["CODING_TOOLS_MCP_OAUTH_CLIENT_ID"] = get_or_create_oauth_client_id()
    env["CODING_TOOLS_MCP_OAUTH_CLIENT_SECRET"] = get_or_create_oauth_client_secret()
    if server_url:
        env["CODING_TOOLS_MCP_SERVER_URL"] = server_url.rstrip("/")
    log_file = LOGS / f"chatgpt-web-mcp-{port}.log"
    with log_file.open("w", encoding="utf-8") as log_handle:
        log_handle.write(f"launcher server_url={env.get('CODING_TOOLS_MCP_SERVER_URL', '<dynamic>')}\n")
        log_handle.flush()
        if os.name == "nt":
            proc = subprocess.Popen(
                args,
                cwd=workspace_path,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=env,
            )
        else:
            proc = subprocess.Popen(args, cwd=workspace_path, stdout=log_handle, stderr=subprocess.STDOUT, env=env)
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return proc


def start_cloudflared_tunnel(port: int) -> subprocess.Popen:
    ensure_dirs()
    command = cloudflared_command()
    if not command:
        raise RuntimeError("cloudflared was not found in PATH.")

    TUNNEL_URL_FILE.unlink(missing_ok=True)
    log_file = LOGS / f"cloudflared-{port}.log"
    TUNNEL_LOG_FILE.write_text(str(log_file), encoding="utf-8")
    args = [command, "tunnel", "--protocol", "http2", "--url", f"http://{DEFAULT_HOST}:{port}"]
    with log_file.open("w", encoding="utf-8") as log_handle:
        if os.name == "nt":
            proc = subprocess.Popen(
                args,
                cwd=ROOT,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=build_env(),
            )
        else:
            proc = subprocess.Popen(args, cwd=ROOT, stdout=log_handle, stderr=subprocess.STDOUT, env=build_env())
    TUNNEL_PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    wait_for_tunnel_url(timeout_seconds=30)
    return proc


def start_cloudflared_named_tunnel(token: str, port: int) -> subprocess.Popen:
    ensure_dirs()
    command = cloudflared_command()
    if not command:
        raise RuntimeError("cloudflared was not found in PATH.")
    token = token.strip()

    TUNNEL_URL_FILE.unlink(missing_ok=True)
    log_file = LOGS / f"cloudflared-named-{port}.log"
    TUNNEL_LOG_FILE.write_text(str(log_file), encoding="utf-8")
    config_file = named_tunnel_config_path()
    if token:
        args = [command, "tunnel", "run", "--token", token]
    elif config_file.exists():
        args = [command, "tunnel", "--config", str(config_file), "run"]
    else:
        raise RuntimeError(f"Named tunnel requires a token or runtime config file: {config_file}")
    with log_file.open("w", encoding="utf-8") as log_handle:
        if os.name == "nt":
            proc = subprocess.Popen(
                args,
                cwd=ROOT,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=build_env(),
            )
        else:
            proc = subprocess.Popen(args, cwd=ROOT, stdout=log_handle, stderr=subprocess.STDOUT, env=build_env())
    TUNNEL_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return proc


def wait_for_public_oauth_metadata(tunnel_url: str, timeout_seconds: float = 90.0) -> tuple[bool, str]:
    expected_base_url = tunnel_url.rstrip("/")
    metadata_url = tunnel_url.rstrip("/") + "/.well-known/oauth-authorization-server"
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            request = urllib.request.Request(metadata_url, headers={"User-Agent": "coding-tools-launcher"})
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read().decode("utf-8", errors="replace")
            if response.status == 200 and "authorization_endpoint" in body:
                metadata = json.loads(body)
                issuer = str(metadata.get("issuer", "")).rstrip("/")
                authorization_endpoint = str(metadata.get("authorization_endpoint", ""))
                token_endpoint = str(metadata.get("token_endpoint", ""))
                if (
                    issuer == expected_base_url
                    and authorization_endpoint.startswith(expected_base_url + "/")
                    and token_endpoint.startswith(expected_base_url + "/")
                ):
                    return True, body
                return False, f"OAuth metadata URL mismatch: issuer={issuer or '<missing>'}, expected={expected_base_url}"
                return False, last_error
            elif response.status == 200:
                last_error = "Unexpected metadata response: missing authorization_endpoint"
            else:
                last_error = f"Unexpected metadata response: HTTP {response.status}"
        except json.JSONDecodeError as exc:
            last_error = f"Invalid OAuth metadata JSON: {exc}"
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.reason}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    return False, last_error


def show_environment(pause_after: bool = True) -> None:
    title()
    print("Environment")
    print(f"- uv: {'found' if which('uv') else 'not found'}")
    print(f"- python: {'found' if which('python') else 'not found'}")
    print(f"- .venv: {'ready' if is_venv_ready() else 'missing'}")
    print(f"- coding-tools-mcp: {'found' if venv_mcp().exists() else 'not found'}")
    print(f"- proxy: {current_proxy_summary()}")
    print(f"- codex config: {next((str(item.path) for item in codex_config_candidates() if item.exists), 'none found')}")
    if pause_after:
        pause()


def create_venv(pause_after: bool = True) -> None:
    title()
    print("Creating .venv with uv...")
    subprocess.run(["uv", "venv", ".venv"], cwd=ROOT, check=True, env=build_env())
    if pause_after:
        pause()


def install_package(pause_after: bool = True) -> None:
    title()
    if not is_venv_ready():
        print("Create .venv first.")
        if pause_after:
            pause()
        return
    print("Installing coding-tools-mcp into .venv...")
    subprocess.run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"], cwd=ROOT, check=True, env=build_env())
    subprocess.run([str(venv_python()), "-m", "pip", "install", "--upgrade", "coding-tools-mcp"], cwd=ROOT, check=True, env=build_env())
    subprocess.run([str(venv_mcp()), "--help"], cwd=ROOT, check=True, env=build_env())
    if pause_after:
        pause()


def stop_server(pause_after: bool = True) -> None:
    title()
    running = load_pid()
    if not running:
        print("No running server.")
        if pause_after:
            pause()
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(running.pid), "/T", "/F"], check=False, env=build_env())
    else:
        subprocess.run(["kill", str(running.pid)], check=False, env=build_env())
    PID_FILE.unlink(missing_ok=True)
    print("Server stopped.")
    if pause_after:
        pause()


def stop_tunnel_process() -> None:
    running = load_tunnel_pid()
    if not running:
        TUNNEL_PID_FILE.unlink(missing_ok=True)
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(running.pid), "/T", "/F"], check=False, env=build_env())
    else:
        subprocess.run(["kill", str(running.pid)], check=False, env=build_env())
    TUNNEL_PID_FILE.unlink(missing_ok=True)
    TUNNEL_URL_FILE.unlink(missing_ok=True)
    TUNNEL_LOG_FILE.unlink(missing_ok=True)


def start_server(pause_after: bool = True) -> None:
    ensure_dirs()
    title()
    running = load_pid()
    if running and process_alive(running.pid):
        print(f"Server already running. PID: {running.pid}")
        if pause_after:
            pause()
        return
    if not venv_mcp().exists():
        print("Install coding-tools-mcp first.")
        if pause_after:
            pause()
        return

    workspace = prompt(str(DEFAULT_WORKSPACE), "Workspace")
    port_text = prompt(str(DEFAULT_PORT), "Port")
    tool_profile = prompt_choice(DEFAULT_TOOL_PROFILE, "Tool profile", {"full", "read-only", "compat-readonly-all"})
    permission_mode = prompt_choice(DEFAULT_PERMISSION_MODE, "Permission mode", {"safe", "trusted", "dangerous"})
    allow_network = prompt_bool(False, "Allow network tools")

    try:
        workspace_path = Path(workspace).resolve()
    except Exception:
        print("Workspace path invalid.")
        if pause_after:
            pause()
        return

    port = choose_bindable_port(int(port_text))
    if port != int(port_text):
        print(f"Port {port_text} is not bindable; using {port}.")
    log_file = LOGS / f"server-{port}.log"
    args = [
        str(venv_mcp()),
        "--workspace",
        str(workspace_path),
        "--host",
        DEFAULT_HOST,
        "--port",
        str(port),
        "--tool-profile",
        tool_profile,
        "--permission-mode",
        permission_mode,
    ]
    if allow_network:
        args.append("--allow-network")

    if any(build_env().get(name) for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")):
        print(f"Proxy active: {current_proxy_summary()}")

    with log_file.open("a", encoding="utf-8") as log_handle:
        if os.name == "nt":
            proc = subprocess.Popen(
                args,
                cwd=workspace_path,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=build_env(),
            )
        else:
            proc = subprocess.Popen(
                args,
                cwd=workspace_path,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=build_env(),
            )

    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    healthy = wait_for_port(DEFAULT_HOST, port)
    print("Server started." if healthy else "Server launched, but health check did not confirm the port yet.")
    print(f"PID: {proc.pid}")
    print(f"URL: http://{DEFAULT_HOST}:{port}/mcp")
    print(f"Log: {log_file}")
    print(f"Health: {'ok' if healthy else 'pending'}")
    if pause_after:
        pause()


def write_snippet(pause_after: bool = True) -> None:
    ensure_dirs()
    title()
    port_text = prompt(str(DEFAULT_PORT), "Port")
    port = int(port_text)
    snippet = render_snippet(port)
    SNIPPET_FILE.write_text(snippet, encoding="utf-8")
    print(f"Saved: {SNIPPET_FILE}")
    print()
    print(snippet)

    candidates = codex_config_candidates()
    existing = [item.path for item in candidates if item.exists]
    if existing:
        print("Existing Codex config file(s) found:")
        for path in existing:
            print(f"- {path}")
    else:
        print("No Codex config file found automatically.")
        print("Likely candidates:")
        for candidate in candidates[:3]:
            print(f"- {candidate.path}")
    if pause_after:
        pause()


def set_proxy(pause_after: bool = True) -> None:
    title()
    current = current_proxy_summary()
    print(f"Current proxy: {current}")
    proxy_url = input("Proxy URL (empty to clear): ").strip()
    if proxy_url:
        save_proxy_settings(proxy_url)
        print(f"Saved proxy settings to {PROXY_FILE}")
    else:
        clear_proxy_settings()
        print("Proxy settings cleared.")
    if pause_after:
        pause()


def bootstrap_all() -> None:
    create_venv(pause_after=False)
    install_package(pause_after=False)
    start_server(pause_after=False)
    write_snippet(pause_after=False)
    pause()


def menu() -> None:
    ensure_dirs()
    while True:
        title()
        running = load_pid()
        server_state = "stopped"
        if running and process_alive(running.pid):
            server_state = f"running (PID {running.pid})"
        elif running:
            server_state = f"stale PID {running.pid}"

        print("Status panel")
        print(f"- server: {server_state}")
        print(f"- venv: {'ready' if is_venv_ready() else 'missing'}")
        print(f"- package: {'ready' if venv_mcp().exists() else 'missing'}")
        print(f"- proxy: {current_proxy_summary()}")
        print(f"- codex config: {next((str(item.path) for item in codex_config_candidates() if item.exists), 'not found')}")
        print()
        print("1) Check environment")
        print("2) Create .venv with uv")
        print("3) Install/upgrade coding-tools-mcp")
        print("4) Start local MCP server")
        print("5) Stop local MCP server")
        print("6) Generate Codex config snippet")
        print("7) Show Codex config candidates")
        print("8) Set or clear proxy")
        print("9) Bootstrap all")
        print("0) Exit")
        print()

        choice = input("Choose: ").strip()
        if choice == "1":
            show_environment()
        elif choice == "2":
            create_venv()
        elif choice == "3":
            install_package()
        elif choice == "4":
            start_server()
        elif choice == "5":
            stop_server()
        elif choice == "6":
            write_snippet()
        elif choice == "7":
            display_codex_configs()
        elif choice == "8":
            set_proxy()
        elif choice == "9":
            bootstrap_all()
        elif choice == "0":
            return
        else:
            print("Unknown option.")
            pause()


if __name__ == "__main__":
    menu()
