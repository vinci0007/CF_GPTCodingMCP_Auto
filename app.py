from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import launcher


class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Coding Tools MCP Launcher")
        self.geometry("1180x760")
        self.minsize(980, 620)

        self.workspace_var = tk.StringVar(value=str(launcher.DEFAULT_WORKSPACE))
        self.port_var = tk.StringVar(value=str(launcher.DEFAULT_PORT))
        self.tool_profile_var = tk.StringVar(value=launcher.DEFAULT_TOOL_PROFILE)
        self.permission_mode_var = tk.StringVar(value=launcher.DEFAULT_PERMISSION_MODE)
        self.allow_network_var = tk.BooleanVar(value=False)
        self.proxy_enabled_var = tk.BooleanVar(value=launcher.proxy_enabled())
        self.proxy_protocol_var = tk.StringVar(value="http")
        self.proxy_host_var = tk.StringVar(value="127.0.0.1")
        self.proxy_port_var = tk.StringVar(value="20100")
        self.proxy_url_var = tk.StringVar(value=launcher.current_proxy_summary() if launcher.current_proxy_summary() != "none" else "")
        self.tunnel_mode_var = tk.StringVar(value="quick")
        self.tunnel_url_var = tk.StringVar(value=launcher.latest_named_tunnel_url() or launcher.latest_tunnel_url() or "")
        self.named_tunnel_token_var = tk.StringVar(value=launcher.latest_named_tunnel_token() or "")
        self.chatgpt_permission_mode_var = tk.StringVar(value="trusted")
        self.oauth_password_var = tk.StringVar(value=launcher.latest_oauth_password() or "")
        self.oauth_client_id_var = tk.StringVar(value=launcher.latest_oauth_client_id() or launcher.get_or_create_oauth_client_id())
        self.oauth_client_secret_var = tk.StringVar(value=launcher.latest_oauth_client_secret() or launcher.get_or_create_oauth_client_secret())
        self.status_var = tk.StringVar(value="Ready")
        self.projects: list[launcher.ProjectEntry] = []
        self._closing = False

        self._build_ui()
        self.load_projects()
        self.refresh_status()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="Coding Tools MCP Launcher", font=("Segoe UI", 16, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(outer, text="Project-local runtime. No default writes to C:.")
        subtitle.pack(anchor=tk.W, pady=(2, 14))

        main = ttk.Frame(outer)
        main.pack(fill=tk.BOTH, expand=True)

        project_frame = ttk.LabelFrame(main, text="Projects", padding=10)
        project_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))
        self.project_list = tk.Listbox(project_frame, width=34, height=18)
        self.project_list.pack(fill=tk.BOTH, expand=True)
        self.project_list.bind("<<ListboxSelect>>", self.on_project_selected)

        project_buttons = ttk.Frame(project_frame)
        project_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(project_buttons, text="Add", command=self.add_project).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(project_buttons, text="Remove", command=self.remove_selected_project).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(project_buttons, text="Switch", command=lambda: self.run_background(self.switch_project)).pack(side=tk.LEFT)

        right_shell = ttk.Frame(main)
        right_shell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_canvas = tk.Canvas(right_shell, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_shell, orient=tk.VERTICAL, command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=right_scrollbar.set)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(self.right_canvas)
        right_window = self.right_canvas.create_window((0, 0), window=right, anchor=tk.NW)

        def update_scroll_region(_event=None) -> None:
            self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))

        def update_canvas_width(event) -> None:
            self.right_canvas.itemconfigure(right_window, width=event.width)

        right.bind("<Configure>", update_scroll_region)
        self.right_canvas.bind("<Configure>", update_canvas_width)
        self.right_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        settings = ttk.LabelFrame(outer, text="Server Settings", padding=12)
        settings.pack_forget()
        settings = ttk.LabelFrame(right, text="Server Settings", padding=12)
        settings.pack(fill=tk.X)

        ttk.Label(settings, text="Workspace").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(settings, textvariable=self.workspace_var).grid(row=0, column=1, sticky=tk.EW, pady=4)
        ttk.Button(settings, text="Browse", command=self.pick_workspace).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(settings, text="Port").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(settings, textvariable=self.port_var, width=12).grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(settings, text="Tool profile").grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.tool_profile_var,
            values=("read-only", "full", "compat-readonly-all"),
            state="readonly",
            width=24,
        ).grid(row=2, column=1, sticky=tk.W, pady=4)

        ttk.Label(settings, text="Permission mode").grid(row=3, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.permission_mode_var,
            values=("safe", "trusted", "dangerous"),
            state="readonly",
            width=24,
        ).grid(row=3, column=1, sticky=tk.W, pady=4)

        ttk.Checkbutton(settings, text="Allow network tools", variable=self.allow_network_var).grid(
            row=4, column=1, sticky=tk.W, pady=4
        )

        proxy_frame = ttk.LabelFrame(settings, text="Proxy", padding=8)
        proxy_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        proxy_frame.columnconfigure(4, weight=1)

        ttk.Checkbutton(proxy_frame, text="Enable", variable=self.proxy_enabled_var).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4
        )
        ttk.Combobox(
            proxy_frame,
            textvariable=self.proxy_protocol_var,
            values=("http", "socks5"),
            state="readonly",
            width=8,
        ).grid(row=0, column=1, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(proxy_frame, textvariable=self.proxy_host_var, width=18).grid(
            row=0, column=2, sticky=tk.W, padx=(0, 8), pady=4
        )
        ttk.Entry(proxy_frame, textvariable=self.proxy_port_var, width=8).grid(
            row=0, column=3, sticky=tk.W, padx=(0, 8), pady=4
        )
        ttk.Entry(proxy_frame, textvariable=self.proxy_url_var).grid(
            row=0, column=4, sticky=tk.EW, padx=(0, 8), pady=4
        )
        ttk.Button(proxy_frame, text="Use 20100", command=self.use_20100_proxy).grid(
            row=0, column=5, sticky=tk.W, padx=(0, 8), pady=4
        )
        ttk.Button(proxy_frame, text="Save", command=self.save_proxy).grid(row=0, column=6, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Button(proxy_frame, text="Clear", command=self.clear_proxy).grid(row=0, column=7, sticky=tk.W, pady=4)

        settings.columnconfigure(1, weight=1)

        buttons = ttk.Frame(outer)
        buttons.pack_forget()
        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=14)

        ttk.Button(buttons, text="Create .venv", command=lambda: self.run_background(self.create_venv)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(buttons, text="Install MCP", command=lambda: self.run_background(self.install_package)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(buttons, text="Start Server", command=lambda: self.run_background(self.start_server)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(buttons, text="Stop Server", command=lambda: self.run_background(self.stop_server)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(buttons, text="Generate Snippet", command=self.generate_snippet).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Refresh", command=self.refresh_status).pack(side=tk.LEFT)

        web_frame = ttk.LabelFrame(outer, text="ChatGPT Web Mode", padding=12)
        web_frame.pack_forget()
        web_frame = ttk.LabelFrame(right, text="ChatGPT Web Mode", padding=12)
        web_frame.pack(fill=tk.X, pady=(0, 14))
        web_frame.columnconfigure(1, weight=1)
        ttk.Label(web_frame, text="Tunnel URL").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(web_frame, textvariable=self.tunnel_url_var).grid(row=0, column=1, sticky=tk.EW, pady=4)
        ttk.Button(web_frame, text="Start OAuth MCP + Tunnel", command=lambda: self.run_background(self.start_chatgpt_web_mode)).grid(
            row=0, column=2, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Button(web_frame, text="Copy MCP URL", command=self.copy_chatgpt_mcp_url).grid(
            row=0, column=3, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Button(web_frame, text="Stop Tunnel", command=lambda: self.run_background(self.stop_tunnel)).grid(
            row=0, column=4, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Button(web_frame, text="Install cloudflared", command=lambda: self.run_background(self.install_cloudflared)).grid(
            row=0, column=5, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Button(web_frame, text="Test OAuth", command=lambda: self.run_background(self.test_oauth_metadata)).grid(
            row=0, column=6, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Label(web_frame, text="Tunnel mode").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Combobox(
            web_frame,
            textvariable=self.tunnel_mode_var,
            values=("quick", "named"),
            state="readonly",
            width=16,
        ).grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(web_frame, text="Named token").grid(row=1, column=2, sticky=tk.W, padx=(8, 0), pady=4)
        ttk.Entry(web_frame, textvariable=self.named_tunnel_token_var, show="*").grid(
            row=1, column=3, columnspan=4, sticky=tk.EW, padx=(8, 0), pady=4
        )
        ttk.Label(web_frame, text="OAuth password").grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(web_frame, textvariable=self.oauth_password_var, show="*").grid(row=2, column=1, sticky=tk.EW, pady=4)
        ttk.Button(web_frame, text="Copy Password", command=self.copy_oauth_password).grid(
            row=2, column=2, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Button(web_frame, text="Reset Password", command=self.reset_oauth_password).grid(
            row=2, column=3, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Label(web_frame, text="Client ID").grid(row=3, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(web_frame, textvariable=self.oauth_client_id_var).grid(row=3, column=1, sticky=tk.EW, pady=4)
        ttk.Button(web_frame, text="Copy Client ID", command=self.copy_oauth_client_id).grid(
            row=3, column=2, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Label(web_frame, text="Client Secret").grid(row=4, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(web_frame, textvariable=self.oauth_client_secret_var, show="*").grid(row=4, column=1, sticky=tk.EW, pady=4)
        ttk.Button(web_frame, text="Copy Secret", command=self.copy_oauth_client_secret).grid(
            row=4, column=2, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Button(web_frame, text="Reset Client", command=self.reset_oauth_client).grid(
            row=4, column=3, sticky=tk.W, padx=(8, 0), pady=4
        )
        ttk.Label(web_frame, text="Web permission").grid(row=5, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Combobox(
            web_frame,
            textvariable=self.chatgpt_permission_mode_var,
            values=("trusted", "dangerous"),
            state="readonly",
            width=16,
        ).grid(row=5, column=1, sticky=tk.W, pady=4)
        ttk.Label(
            web_frame,
            text="Use dangerous only for trusted projects when ChatGPT must write files.",
        ).grid(row=5, column=2, columnspan=5, sticky=tk.W, padx=(8, 0), pady=4)

        status = ttk.LabelFrame(outer, text="Status", padding=12)
        status.pack_forget()
        status = ttk.LabelFrame(right, text="Status", padding=12)
        status.pack(fill=tk.X)
        status_body = ttk.Frame(status)
        status_body.pack(fill=tk.X)
        self.status_text = tk.Text(status_body, height=7, wrap=tk.WORD)
        status_scroll = ttk.Scrollbar(status_body, orient=tk.VERTICAL, command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=status_scroll.set)
        status_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        log_frame = ttk.LabelFrame(outer, text="Log", padding=12)
        log_frame.pack_forget()
        log_frame = ttk.LabelFrame(right, text="Log", padding=12)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        log_body = ttk.Frame(log_frame)
        log_body.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_body, height=12, wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(log_body, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(bottom, textvariable=self.status_var).pack(side=tk.LEFT)

    def append_log(self, message: str) -> None:
        if threading.current_thread() is not threading.main_thread():
            self.after(0, lambda: self.append_log(message))
            return
        self.log_text.insert(tk.END, message.rstrip() + "\n")
        self.log_text.see(tk.END)

    def refresh_status(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.refresh_status)
            return
        running = launcher.load_pid()
        if running and launcher.process_alive(running.pid):
            server_state = f"running (PID {running.pid})"
        elif running:
            server_state = f"stale PID {running.pid}"
        else:
            server_state = "stopped"

        configs = launcher.codex_config_candidates()
        existing_configs = [str(item.path) for item in configs if item.exists]
        status = "\n".join(
            [
                f"Server: {server_state}",
                f"Cloudflared: {self.tunnel_state()}",
                f"Venv: {'ready' if launcher.is_venv_ready() else 'missing'}",
                f"Package: {'ready' if launcher.venv_mcp().exists() else 'missing'}",
                f"Cloudflared installed: {'yes' if launcher.cloudflared_command() else 'no'}",
                f"Proxy: {launcher.current_proxy_summary()}",
                f"Snippet: {launcher.SNIPPET_FILE}",
                "Codex config: " + (existing_configs[0] if existing_configs else "not found automatically"),
            ]
        )
        self.tunnel_url_var.set(launcher.latest_named_tunnel_url() or launcher.latest_tunnel_url() or "")
        self.oauth_password_var.set(launcher.latest_oauth_password() or self.oauth_password_var.get())
        self.oauth_client_id_var.set(launcher.latest_oauth_client_id() or self.oauth_client_id_var.get())
        self.oauth_client_secret_var.set(launcher.latest_oauth_client_secret() or self.oauth_client_secret_var.get())
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert(tk.END, status)

    def tunnel_state(self) -> str:
        running = launcher.load_tunnel_pid()
        if running and launcher.process_alive(running.pid):
            return f"running (PID {running.pid})"
        if running:
            return f"stale PID {running.pid}"
        return "stopped"

    def run_background(self, action) -> None:
        def worker() -> None:
            try:
                if self._closing:
                    return
                self.after(0, lambda: self.status_var.set("Working..."))
                action()
                if not self._closing:
                    self.after(0, lambda: self.status_var.set("Done"))
            except Exception as exc:
                if self._closing:
                    return
                error_message = str(exc)
                self.after(0, lambda: self.status_var.set("Failed"))
                self.append_log(f"Error: {error_message}")
                self.after(0, lambda message=error_message: messagebox.showerror("Launcher error", message))
            finally:
                if not self._closing:
                    self.after(0, self.refresh_status)

        threading.Thread(target=worker, daemon=True).start()

    def on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.status_var.set("Closing...")
        try:
            launcher.stop_tunnel_process()
            running = launcher.load_pid()
            if running:
                if launcher.os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(running.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=launcher.build_env(),
                    )
                else:
                    subprocess.run(
                        ["kill", str(running.pid)],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=launcher.build_env(),
                    )
                launcher.PID_FILE.unlink(missing_ok=True)
        finally:
            self.destroy()

    def on_mousewheel(self, event) -> None:
        if not hasattr(self, "right_canvas"):
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget in {self.log_text, self.status_text, self.project_list}:
            return
        self.right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def pick_workspace(self) -> None:
        path = filedialog.askdirectory(initialdir=self.workspace_var.get())
        if path:
            self.workspace_var.set(path)
            self.add_project_from_path(Path(path))

    def load_projects(self) -> None:
        self.projects = launcher.list_projects()
        self.project_list.delete(0, tk.END)
        current = launcher.current_project_path()
        selected_index = 0
        for index, project in enumerate(self.projects):
            self.project_list.insert(tk.END, f"{project.name}  |  {project.path}")
            if project.path == current:
                selected_index = index
        if self.projects:
            self.project_list.selection_clear(0, tk.END)
            self.project_list.selection_set(selected_index)
            self.project_list.activate(selected_index)
            self.apply_project(self.projects[selected_index])

    def selected_project(self) -> launcher.ProjectEntry | None:
        selection = self.project_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index < 0 or index >= len(self.projects):
            return None
        return self.projects[index]

    def apply_project(self, project: launcher.ProjectEntry) -> None:
        self.workspace_var.set(project.path)
        self.port_var.set(str(project.port))
        self.tool_profile_var.set(project.tool_profile)
        self.permission_mode_var.set(project.permission_mode)
        self.allow_network_var.set(project.allow_network)

    def save_current_project_settings(self) -> None:
        workspace = Path(self.workspace_var.get()).resolve()
        launcher.upsert_project(
            launcher.ProjectEntry(
                name=launcher.project_name_from_path(workspace),
                path=str(workspace),
                port=int(self.port_var.get()),
                tool_profile=self.tool_profile_var.get(),
                permission_mode=self.permission_mode_var.get(),
                allow_network=self.allow_network_var.get(),
            ),
            make_current=True,
        )
        if threading.current_thread() is threading.main_thread():
            self.load_projects()
        else:
            self.after(0, self.load_projects)

    def add_project(self) -> None:
        path = filedialog.askdirectory(initialdir=self.workspace_var.get())
        if path:
            self.add_project_from_path(Path(path))

    def add_project_from_path(self, path: Path) -> None:
        resolved = path.resolve()
        launcher.upsert_project(
            launcher.ProjectEntry(
                name=launcher.project_name_from_path(resolved),
                path=str(resolved),
                port=int(self.port_var.get()),
                tool_profile=self.tool_profile_var.get(),
                permission_mode=self.permission_mode_var.get(),
                allow_network=self.allow_network_var.get(),
            ),
            make_current=True,
        )
        self.load_projects()
        self.append_log(f"Added project: {resolved}")

    def remove_selected_project(self) -> None:
        project = self.selected_project()
        if not project:
            return
        launcher.remove_project(project.path)
        self.load_projects()
        self.append_log(f"Removed project: {project.path}")

    def on_project_selected(self, _event=None) -> None:
        project = self.selected_project()
        if project:
            self.apply_project(project)

    def switch_project(self) -> None:
        project = self.selected_project()
        if not project:
            raise RuntimeError("Select a project first.")
        self.apply_project(project)
        launcher.upsert_project(project, make_current=True)
        launcher.stop_tunnel_process()
        self.stop_server()
        self.start_server()
        self.append_log(f"Switched to project: {project.path}")

    def save_proxy(self) -> None:
        if not self.proxy_url_var.get().strip():
            self.proxy_url_var.set(
                launcher.normalize_proxy_url(
                    self.proxy_protocol_var.get(),
                    self.proxy_host_var.get(),
                    self.proxy_port_var.get(),
                )
            )

        proxy = self.proxy_url_var.get().strip()
        if self.proxy_enabled_var.get() and proxy:
            launcher.save_proxy_settings(proxy)
            self.append_log(f"Saved proxy: {proxy}")
        else:
            launcher.clear_proxy_settings()
            self.append_log("Cleared proxy settings.")
        self.refresh_status()

    def clear_proxy(self) -> None:
        self.proxy_enabled_var.set(False)
        self.proxy_url_var.set("")
        launcher.clear_proxy_settings()
        self.append_log("Cleared proxy settings.")
        self.refresh_status()

    def use_20100_proxy(self) -> None:
        self.proxy_enabled_var.set(True)
        self.proxy_protocol_var.set("http")
        self.proxy_host_var.set("127.0.0.1")
        self.proxy_port_var.set("20100")
        self.proxy_url_var.set("http://127.0.0.1:20100")
        self.save_proxy()

    def create_venv(self) -> None:
        self.append_log("Creating .venv...")
        subprocess.run(["uv", "venv", ".venv"], cwd=launcher.ROOT, check=True, env=launcher.build_env())
        self.append_log("Created .venv.")

    def install_package(self) -> None:
        if not launcher.is_venv_ready():
            raise RuntimeError("Create .venv first.")
        self.append_log("Installing coding-tools-mcp...")
        subprocess.run(
            [str(launcher.venv_python()), "-m", "pip", "install", "--upgrade", "pip"],
            cwd=launcher.ROOT,
            check=True,
            env=launcher.build_env(),
        )
        subprocess.run(
            [str(launcher.venv_python()), "-m", "pip", "install", "--upgrade", "coding-tools-mcp"],
            cwd=launcher.ROOT,
            check=True,
            env=launcher.build_env(),
        )
        self.append_log("Installed coding-tools-mcp.")

    def start_server(self) -> None:
        self.save_current_project_settings()
        running = launcher.load_pid()
        if running and launcher.process_alive(running.pid):
            self.append_log(f"Server already running: PID {running.pid}")
            return
        if not launcher.venv_mcp().exists():
            raise RuntimeError("Install coding-tools-mcp first.")

        workspace = Path(self.workspace_var.get()).resolve()
        requested_port = int(self.port_var.get())
        port = launcher.choose_bindable_port(requested_port)
        if port != requested_port:
            self.after(0, lambda: self.port_var.set(str(port)))
            self.append_log(f"Port {requested_port} is not bindable; using {port}.")
        log_file = launcher.LOGS / f"server-{port}.log"
        launcher.ensure_dirs()

        args = [
            str(launcher.venv_mcp()),
            "--workspace",
            str(workspace),
            "--host",
            launcher.DEFAULT_HOST,
            "--port",
            str(port),
            "--tool-profile",
            self.tool_profile_var.get(),
            "--permission-mode",
            self.permission_mode_var.get(),
        ]
        if self.allow_network_var.get():
            args.append("--allow-network")

        with log_file.open("a", encoding="utf-8") as log_handle:
            if launcher.os.name == "nt":
                proc = subprocess.Popen(
                    args,
                    cwd=workspace,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    env=launcher.build_env(),
                )
            else:
                proc = subprocess.Popen(
                    args,
                    cwd=workspace,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=launcher.build_env(),
                )
        launcher.PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        healthy = launcher.wait_for_port(launcher.DEFAULT_HOST, port)
        self.append_log(f"Server PID: {proc.pid}")
        self.append_log(f"URL: http://{launcher.DEFAULT_HOST}:{port}/mcp")
        self.append_log(f"Health: {'ok' if healthy else 'pending'}")
        self.append_log(f"Log file: {log_file}")

    def stop_server(self) -> None:
        running = launcher.load_pid()
        if not running:
            self.append_log("No running server.")
            return
        if launcher.os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(running.pid), "/T", "/F"], check=False, env=launcher.build_env())
        else:
            subprocess.run(["kill", str(running.pid)], check=False, env=launcher.build_env())
        launcher.PID_FILE.unlink(missing_ok=True)
        self.append_log("Server stopped.")

    def generate_snippet(self) -> None:
        self.save_current_project_settings()
        port = int(self.port_var.get())
        snippet = launcher.render_snippet(port)
        launcher.ensure_dirs()
        launcher.SNIPPET_FILE.write_text(snippet, encoding="utf-8")
        self.append_log(f"Saved snippet: {launcher.SNIPPET_FILE}")
        self.append_log(snippet)
        messagebox.showinfo("Snippet generated", f"Saved to:\n{launcher.SNIPPET_FILE}")
        self.refresh_status()

    def start_chatgpt_web_mode(self) -> None:
        self.save_current_project_settings()
        if not launcher.cloudflared_command():
            self.append_log("cloudflared not found. Installing locally into .runtime/bin...")
            launcher.install_cloudflared_local()
            self.append_log(f"Installed cloudflared: {launcher.local_cloudflared_path()}")

        launcher.stop_tunnel_process()
        existing = launcher.load_pid()
        if existing and launcher.process_alive(existing.pid):
            self.append_log(f"Stopping existing MCP server: PID {existing.pid}")
        self.stop_server()

        if not launcher.venv_mcp().exists():
            raise RuntimeError("Install coding-tools-mcp first.")
        web_permission_mode = self.chatgpt_permission_mode_var.get()
        self.append_log(f"ChatGPT Web tools: profile=full, permission={web_permission_mode}, apply_patch=enabled")
        launcher.OAUTH_CLIENT_ID_FILE.write_text(self.oauth_client_id_var.get().strip(), encoding="utf-8")
        launcher.OAUTH_CLIENT_SECRET_FILE.write_text(self.oauth_client_secret_var.get().strip(), encoding="utf-8")
        launcher.OAUTH_PASSWORD_FILE.write_text(self.oauth_password_var.get().strip(), encoding="utf-8")
        workspace = Path(self.workspace_var.get()).resolve()
        requested_port = int(self.port_var.get())
        port = launcher.choose_bindable_port(requested_port)
        if port != requested_port:
            self.after(0, lambda: self.port_var.set(str(port)))
            self.append_log(f"Port {requested_port} is not bindable; using {port}.")
        tunnel_mode = self.tunnel_mode_var.get()
        if tunnel_mode == "named":
            url = self.tunnel_url_var.get().strip().rstrip("/")
            token = self.named_tunnel_token_var.get().strip()
            if not url:
                raise RuntimeError("Named tunnel mode requires a fixed public Tunnel URL.")
            if not token:
                raise RuntimeError("Named tunnel mode requires a Cloudflare Tunnel token.")
            launcher.save_named_tunnel_settings(url, token)
            proc = launcher.start_chatgpt_web_server(
                workspace_path=workspace,
                port=port,
                server_url=url,
                tool_profile="full",
                permission_mode=web_permission_mode,
                allow_network=True,
                strict_port=True,
            )
            self.append_log(f"Started OAuth MCP server with named public URL: PID {proc.pid}")
            if not launcher.wait_for_port(launcher.DEFAULT_HOST, port):
                raise RuntimeError("OAuth MCP server did not pass local port health check.")
            proc = launcher.start_cloudflared_named_tunnel(token, port)
            self.append_log(f"Started named cloudflared tunnel: PID {proc.pid}")
            self.append_log("Waiting for named public OAuth metadata...")
            ready, detail = launcher.wait_for_public_oauth_metadata(url)
            if not ready:
                self.append_log(f"Public OAuth metadata not ready: {detail}")
                raise RuntimeError("Named tunnel started, but the fixed URL is not routing to this MCP server yet. Check Cloudflare public hostname service URL and token.")
            self.append_log("Public OAuth metadata OK.")
            self.after(0, lambda: self.tunnel_url_var.set(url))
            password = launcher.latest_oauth_password() or self.oauth_password_var.get()
            self.after(0, lambda: self.oauth_password_var.set(password))
            self.append_log(f"ChatGPT MCP URL: {url}/mcp")
            self.append_log("OAuth password is shown in the ChatGPT Web Mode panel.")
            self.append_log("If ChatGPT still cannot see apply_patch, refresh the app details page or reconnect the MCP app.")
            return
        proc = launcher.start_chatgpt_web_server(
            workspace_path=workspace,
            port=port,
            tool_profile="full",
            permission_mode=web_permission_mode,
            allow_network=True,
            strict_port=True,
        )
        self.append_log(f"Started OAuth MCP server for tunnel bootstrap: PID {proc.pid}")

        port = int(self.port_var.get())
        if not launcher.wait_for_port(launcher.DEFAULT_HOST, port):
            raise RuntimeError("MCP server did not pass local port health check.")

        tunnel = launcher.load_tunnel_pid()
        if tunnel and launcher.process_alive(tunnel.pid):
            self.append_log(f"Cloudflared already running: PID {tunnel.pid}")
        else:
            proc = launcher.start_cloudflared_tunnel(port)
            self.append_log(f"Started cloudflared tunnel: PID {proc.pid}")

        self.append_log("Waiting for Cloudflare Tunnel URL...")
        url = launcher.wait_for_tunnel_url(timeout_seconds=30)
        if not url:
            self.append_log("Tunnel URL not found yet. Check .runtime/logs/cloudflared-*.log.")
            return

        self.append_log(f"Restarting OAuth MCP with public server URL: {url}")
        self.stop_server()
        if not launcher.wait_for_port_closed(launcher.DEFAULT_HOST, port):
            raise RuntimeError(f"Port {port} is still occupied after stopping MCP server.")
        proc = launcher.start_chatgpt_web_server(
            workspace_path=workspace,
            port=port,
            server_url=url,
            tool_profile="full",
            permission_mode=web_permission_mode,
            allow_network=True,
            strict_port=True,
        )
        self.append_log(f"Started OAuth MCP server with public URL: PID {proc.pid}")
        if not launcher.wait_for_port(launcher.DEFAULT_HOST, port):
            raise RuntimeError("OAuth MCP server did not pass health check after public URL restart.")

        self.append_log("Waiting for public OAuth metadata...")
        ready, detail = launcher.wait_for_public_oauth_metadata(url)
        if not ready:
            self.append_log(f"Public OAuth metadata not ready: {detail}")
            if "OAuth metadata URL mismatch" in detail:
                raise RuntimeError("OAuth metadata still points to an old Tunnel URL. Stop Server/Tunnel, then start OAuth MCP + Tunnel again.")
            raise RuntimeError("Tunnel URL was created, but Cloudflare did not route to the OAuth server yet. Click Test OAuth or retry Start OAuth MCP + Tunnel.")
        self.append_log("Public OAuth metadata OK.")

        self.after(0, lambda: self.tunnel_url_var.set(url))
        password = launcher.latest_oauth_password() or self.oauth_password_var.get()
        self.after(0, lambda: self.oauth_password_var.set(password))
        self.append_log(f"ChatGPT MCP URL: {url}/mcp")
        self.append_log("OAuth password is shown in the ChatGPT Web Mode panel.")
        self.append_log("If ChatGPT still cannot see apply_patch, refresh the app details page or reconnect the MCP app.")

    def copy_chatgpt_mcp_url(self) -> None:
        url = self.tunnel_url_var.get().strip()
        tunnel = launcher.load_tunnel_pid()
        if not tunnel or not launcher.process_alive(tunnel.pid) or not url:
            self.tunnel_url_var.set("")
            messagebox.showwarning("No live tunnel", "Start ChatGPT Web Mode first, then copy the new MCP URL.")
            return
        mcp_url = url.rstrip("/") + "/mcp"
        self.clipboard_clear()
        self.clipboard_append(mcp_url)
        self.append_log(f"Copied: {mcp_url}")

    def stop_tunnel(self) -> None:
        launcher.stop_tunnel_process()
        self.after(0, lambda: self.tunnel_url_var.set(""))
        self.append_log("Cloudflared tunnel stopped.")

    def install_cloudflared(self) -> None:
        path = launcher.install_cloudflared_local()
        self.append_log(f"cloudflared ready: {path}")

    def copy_oauth_password(self) -> None:
        password = self.oauth_password_var.get().strip()
        if not password:
            password = launcher.get_or_create_oauth_password()
            self.oauth_password_var.set(password)
        self.clipboard_clear()
        self.clipboard_append(password)
        self.append_log("Copied OAuth password.")

    def reset_oauth_password(self) -> None:
        password = launcher.get_or_create_oauth_password(reset=True)
        self.oauth_password_var.set(password)
        self.append_log("Reset OAuth password. Restart OAuth MCP server for it to take effect.")

    def copy_oauth_client_id(self) -> None:
        client_id = self.oauth_client_id_var.get().strip() or launcher.get_or_create_oauth_client_id()
        self.oauth_client_id_var.set(client_id)
        self.clipboard_clear()
        self.clipboard_append(client_id)
        self.append_log("Copied OAuth Client ID.")

    def copy_oauth_client_secret(self) -> None:
        client_secret = self.oauth_client_secret_var.get().strip() or launcher.get_or_create_oauth_client_secret()
        self.oauth_client_secret_var.set(client_secret)
        self.clipboard_clear()
        self.clipboard_append(client_secret)
        self.append_log("Copied OAuth Client Secret.")

    def reset_oauth_client(self) -> None:
        client_id = launcher.get_or_create_oauth_client_id(reset=True)
        client_secret = launcher.get_or_create_oauth_client_secret(reset=True)
        self.oauth_client_id_var.set(client_id)
        self.oauth_client_secret_var.set(client_secret)
        self.append_log("Reset OAuth client. Restart OAuth MCP server for it to take effect.")

    def test_oauth_metadata(self) -> None:
        url = self.tunnel_url_var.get().strip().rstrip("/")
        if not url:
            raise RuntimeError("Start ChatGPT Web Mode first.")
        ready, detail = launcher.wait_for_public_oauth_metadata(url)
        if not ready:
            if "OAuth metadata URL mismatch" in detail:
                raise RuntimeError(f"OAuth metadata points to an old Tunnel URL. Restart Server/Tunnel. Detail: {detail}")
            raise RuntimeError(f"OAuth metadata not reachable: {detail}")
        self.append_log(f"OAuth metadata OK: {url}/.well-known/oauth-authorization-server")
        self.append_log(detail[:1000])


if __name__ == "__main__":
    LauncherApp().mainloop()
