#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared network protocol, UI helpers, and client-side system actions."""
import ctypes
import ipaddress
import io
import json
import os
import platform
import socket
import struct
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlsplit

from PIL import Image, ImageGrab, ImageTk

PORT = 5050

DISCOVERY_PORT = 5051

DISCOVER_MSG = b"LABCONTROL_DISCOVER"

HERE_MSG = b"LABCONTROL_HERE"

IS_WIN = platform.system() == "Windows"

RECV_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Lab Control")

HOSTS = (r"C:\Windows\System32\drivers\etc\hosts" if IS_WIN else "/etc/hosts")

MARK_I, MARK_F = "# LABCONTROL-INICIO", "# LABCONTROL-FIN"

COLORS = {
    "background": "#F3F6FB",
    "surface": "#FFFFFF",
    "navy": "#14243A",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "text": "#172B4D",
    "muted": "#66758A",
    "border": "#DCE4EF",
    "success": "#16835D",
    "warning": "#B7791F",
    "danger": "#C0394B",
}

def setup_theme(root):
    root.configure(bg=COLORS["background"])
    root.option_add("*Font", ("Segoe UI", 10))
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("TFrame", background=COLORS["background"])
    style.configure("Card.TFrame", background=COLORS["surface"])
    style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"])
    style.configure("Card.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
    style.configure("Header.TFrame", background=COLORS["navy"])
    style.configure("Header.TLabel", background=COLORS["navy"], foreground="#FFFFFF")
    style.configure(
        "TButton", padding=(12, 8), background=COLORS["surface"],
        foreground=COLORS["text"], bordercolor=COLORS["border"],
    )
    style.map(
        "TButton",
        background=[("active", "#EAF0F8"), ("pressed", "#DCE7F5")],
        foreground=[("disabled", "#97A3B4")],
    )
    style.configure(
        "Primary.TButton", padding=(14, 9), background=COLORS["primary"],
        foreground="#FFFFFF", bordercolor=COLORS["primary"],
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLORS["primary_hover"]), ("pressed", COLORS["primary_hover"])],
        foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
    )
    style.configure(
        "Danger.TButton", padding=(12, 8), background="#FFF1F2",
        foreground=COLORS["danger"], bordercolor="#F5C8CF",
    )
    style.map("Danger.TButton", background=[("active", "#FFE4E8")])
    style.configure("TRadiobutton", background=COLORS["surface"], foreground=COLORS["text"])
    style.map("TRadiobutton", background=[("active", COLORS["surface"])])
    style.configure(
        "TEntry", padding=(9, 8), fieldbackground=COLORS["surface"],
        foreground=COLORS["text"], bordercolor=COLORS["border"],
    )
    return style

def style_text_widget(widget):
    widget.configure(
        bg=COLORS["surface"], fg=COLORS["text"], insertbackground=COLORS["text"],
        selectbackground="#D9E7FF", relief="flat", borderwidth=0,
        font=("Segoe UI", 10), padx=12, pady=10,
    )

class Conn:
    def __init__(self, sock):
        self.sock = sock
        self.lock = threading.Lock()

    def send(self, header, payload=b""):
        h = json.dumps(header).encode()
        with self.lock:
            self.sock.sendall(struct.pack("!II", len(h), len(payload)) + h + payload)

    def _recvn(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(min(65536, n - len(buf)))
            if not chunk:
                raise ConnectionError("conexión cerrada")
            buf += chunk
        return bytes(buf)

    def recv(self):
        hl, pl = struct.unpack("!II", self._recvn(8))
        if hl > 1_000_000 or pl > 500_000_000:
            raise ConnectionError("mensaje demasiado grande")
        header = json.loads(self._recvn(hl))
        payload = self._recvn(pl) if pl else b""
        return header, payload

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

def capture_jpeg(max_w=1000, quality=50):
    img = ImageGrab.grab()
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()

def save_received(folder, name, data):
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(name) or "archivo"
    path = os.path.join(folder, name)
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(path):
        path = f"{base}_{i}{ext}"
        i += 1
    with open(path, "wb") as f:
        f.write(data)
    return path

def received_dir_for_client(client_index):
    if client_index in (1, 2):
        return os.path.join(RECV_DIR, f"Cliente {client_index}")
    return os.path.join(RECV_DIR, "Administrador")

def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin()) if IS_WIN else os.geteuid() == 0
    except Exception:
        return False

def local_ip():
    """IP local de esta PC en la red actual (no envía tráfico real)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()

def discover_admin(timeout=3.0):
    """Busca al administrador con broadcast UDP. Devuelve su IP o None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.6)
    targets = ["255.255.255.255"]
    ip = local_ip()
    if ip.count(".") == 3:
        targets.append(ip.rsplit(".", 1)[0] + ".255")
    end = time.time() + timeout
    try:
        while time.time() < end:
            for t in targets:
                try:
                    s.sendto(DISCOVER_MSG, (t, DISCOVERY_PORT))
                except Exception:
                    pass
            try:
                data, addr = s.recvfrom(256)
                if data.startswith(HERE_MSG):
                    return addr[0]
            except socket.timeout:
                pass
    finally:
        s.close()
    return None

class Viewer:
    """Ventana que muestra frames JPEG."""

    def __init__(self, root, title, on_close=None):
        self.win = tk.Toplevel(root)
        self.win.title(title)
        self.win.configure(bg=COLORS["navy"])
        self.win.geometry("1000x650")
        self.label = tk.Label(self.win, bg=COLORS["navy"])
        self.label.pack(fill="both", expand=True)
        self.alive = True
        self.on_close = on_close
        self.photo = None
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def show(self, data):
        if not self.alive:
            return
        self.photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))
        self.label.configure(image=self.photo)

    def close(self):
        if self.alive:
            self.alive = False
            self.win.destroy()
            if self.on_close:
                self.on_close()

def set_input_lock(lock):
    if not IS_WIN:
        return False, "Bloqueo de teclado/mouse solo soportado en Windows"
    if not is_admin():
        return False, "Ejecuta el cliente como Administrador"
    ok = ctypes.windll.user32.BlockInput(bool(lock))
    return bool(ok), "OK" if ok else "BlockInput falló"

def shutdown_pc():
    if IS_WIN:
        return run(["shutdown", "/s", "/t", "10", "/c", "Apagado remoto por el administrador"])
    return run(["shutdown", "-h", "+0"])

def _clean_hosts(text):
    out, skip = [], False
    for line in text.splitlines():
        if line.strip() == MARK_I:
            skip = True
            continue
        if line.strip() == MARK_F:
            skip = False
            continue
        if not skip:
            out.append(line)
    return out

def _managed_hosts(text):
    entries, inside = [], False
    for line in text.splitlines():
        marker = line.strip()
        if marker == MARK_I:
            inside = True
        elif marker == MARK_F:
            inside = False
        elif inside and marker:
            entries.append(line)
    return entries

def _site_hosts(sites):
    hosts = set()
    for site in sites:
        value = str(site).strip()
        if not value:
            continue
        parsed = urlsplit(value if "://" in value else "//" + value)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"Sitio web no válido: {value}")
        try:
            host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError(f"Sitio web no válido: {value}") from exc
        labels = host.split(".")
        if (
            len(host) > 253
            or len(labels) < 2
            or any(
                not label or len(label) > 63 or label[0] == "-" or label[-1] == "-"
                or not all(char.isalnum() or char == "-" for char in label)
                for label in labels
            )
        ):
            raise ValueError(f"Sitio web no válido: {value}")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError(f"Escribe un nombre de sitio, no una IP: {value}")
        base = host[4:] if host.startswith("www.") else host
        hosts.update((base, "www." + base))
    return sorted(hosts)

def _write_managed_hosts(text, entries):
    lines = _clean_hosts(text)
    if entries:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend((MARK_I, *entries, MARK_F))
    with open(HOSTS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")

def _flush_hosts_dns():
    if IS_WIN:
        return run(["ipconfig", "/flushdns"])
    return True, ""

def _managed_hostname(line):
    fields = line.split()
    if len(fields) >= 2 and fields[0] in ("0.0.0.0", "127.0.0.1", "::"):
        return fields[1].rstrip(".").lower()
    return None

def block_sites(sites):
    try:
        hosts = _site_hosts(sites)
        if not hosts:
            return False, "Escribe al menos un sitio web"
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        entries = _managed_hosts(text)
        existing = {
            hostname for line in entries
            if (hostname := _managed_hostname(line)) is not None
        }
        entries.extend(
            f"0.0.0.0 {host}" for host in hosts if host not in existing
        )
        _write_managed_hosts(text, entries)
        ok, detail = _flush_hosts_dns()
        if not ok:
            return False, f"Bloqueo guardado, pero no se pudo vaciar la caché DNS: {detail}"
        return True, "Sitios bloqueados: " + ", ".join(hosts)
    except PermissionError:
        return False, "Sin permisos: ejecuta el cliente como Administrador/root"
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def unblock_sites(sites=None):
    try:
        hosts = _site_hosts(sites) if sites else None
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        entries = _managed_hosts(text)
        if hosts is None:
            remaining = []
            message = "Todos los sitios bloqueados fueron desbloqueados"
        else:
            targets = set(hosts)
            remaining = [
                line for line in entries
                if _managed_hostname(line) not in targets
            ]
            message = "Sitios desbloqueados: " + ", ".join(hosts)
        if remaining == entries:
            return True, "No había bloqueos para los sitios indicados"
        _write_managed_hosts(text, remaining)
        ok, detail = _flush_hosts_dns()
        if not ok:
            return False, f"Desbloqueo guardado, pero no se pudo vaciar la caché DNS: {detail}"
        return True, message
    except PermissionError:
        return False, "Sin permisos: ejecuta el cliente como Administrador/root"
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def set_ping(allow, remote_ips=None):
    if remote_ips is not None:
        if not IS_WIN:
            return False, "El control de ping hacia el administrador solo está soportado en Windows"
        if not remote_ips:
            return False, "No hay clientes conectados para aplicar la regla"
        if not is_admin():
            return False, "Ejecuta Lab Control como Administrador para cambiar el firewall"
        try:
            ips = sorted({str(ipaddress.IPv4Address(ip)) for ip in remote_ips})
        except ipaddress.AddressValueError as exc:
            return False, f"IP de cliente no válida: {exc}"
        names = (
            "LABCONTROL_ADMIN_BLOCK_CLIENT_PING",
            "LABCONTROL_ADMIN_ALLOW_CLIENT_PING",
        )
        for name in names:
            run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"])
        action = "allow" if allow else "block"
        name = names[1] if allow else names[0]
        result = run([
            "netsh", "advfirewall", "firewall", "add", "rule", f"name={name}",
            "dir=in", f"action={action}", "protocol=icmpv4:8,any",
            "remoteip=" + ",".join(ips), "profile=any", "enable=yes",
        ])
        if result[0]:
            state = "permitido" if allow else "denegado"
            return True, f"Ping al administrador {state} para los clientes conectados"
        return result

    if IS_WIN:
        legacy_names = ("LAB_BLOCK_PING", "LAB_ALLOW_PING")
        names = ("LABCONTROL_BLOCK_PING", "LABCONTROL_ALLOW_PING")
        for n in legacy_names + names:
            run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={n}"])
        action = "allow" if allow else "block"
        name = names[1] if allow else names[0]
        return run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={name}",
                    "dir=in", f"action={action}", "protocol=icmpv4:8,any",
                    "profile=any", "enable=yes"])
    rule = ["INPUT", "-p", "icmp", "--icmp-type", "echo-request", "-j", "DROP"]
    while run(["iptables", "-D"] + rule)[0]:
        pass
    if allow:
        return True, "Ping permitido"
    return run(["iptables", "-A"] + rule)
