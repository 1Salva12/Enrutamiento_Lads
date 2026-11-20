#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Administrator application for Lab Control."""
import hmac
import io
import os
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from comun import (
    COLORS, Conn, DISCOVERY_PORT, DISCOVER_MSG, HERE_MSG, PORT, RECV_DIR,
    Viewer, capture_jpeg, local_ip, save_received, set_ping, setup_theme,
)

class Peer:
    def __init__(self, conn, name, ip, client_index):
        self.conn, self.name, self.ip = conn, name, ip
        self.client_index = client_index

class AdminApp:
    def __init__(self, root, password):
        self.root, self.password = root, password
        self.peers = []
        self.peers_lock = threading.Lock()
        self.screen_lock = threading.Lock()
        self.screen_watchers = {}
        self.client_shares = {}
        self.client_shares_lock = threading.Lock()
        self.q = queue.Queue()
        self.viewer = None
        self.view_peer = None
        self.sharing = False
        self.monitor_frames = {}
        self.monitor_photos = {}
        self.monitor_source_images = {}
        self.dual_view = False
        self.chat_window = None
        self.chat = None
        self.chat_entry = None
        self.chat_history = []
        for w in root.winfo_children():
            w.destroy()
        setup_theme(root)
        root.title("Lab Control - ADMINISTRADOR")
        root.geometry("1440x900")
        root.minsize(1100, 700)

        header = ttk.Frame(root, style="Header.TFrame", padding=(24, 17))
        header.pack(fill="x")
        header_left = ttk.Frame(header, style="Header.TFrame")
        header_left.pack(side="left", fill="x", expand=True)
        ttk.Label(header_left, text="Lab Control", style="Header.TLabel",
                  font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(header_left, text="Panel de administración del laboratorio",
                  style="Header.TLabel", foreground="#C8D5E6").pack(anchor="w", pady=(3, 0))
        ip = local_ip()
        ttk.Label(header, text=f"●  Admin en red  |  {ip}", style="Header.TLabel",
                  font=("Segoe UI", 10, "bold")).pack(side="right", padx=(12, 0))

        content = tk.Frame(root, bg="#0D1B2A")
        content.pack(fill="both", expand=True)

        left = tk.Frame(content, bg="#0B2A5B", width=330)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        command_canvas = tk.Canvas(left, bg="#0B2A5B", highlightthickness=0, borderwidth=0)
        command_scrollbar = ttk.Scrollbar(left, orient="vertical", command=command_canvas.yview)
        command_canvas.configure(yscrollcommand=command_scrollbar.set)
        command_scrollbar.pack(side="right", fill="y")
        command_canvas.pack(side="left", fill="both", expand=True)
        command_panel = tk.Frame(command_canvas, bg="#0B2A5B")
        command_window = command_canvas.create_window(
            (0, 0), window=command_panel, anchor="nw"
        )
        command_panel.bind(
            "<Configure>",
            lambda event: command_canvas.configure(
                scrollregion=command_canvas.bbox("all")
            ),
        )
        command_canvas.bind(
            "<Configure>",
            lambda event: command_canvas.itemconfigure(
                command_window, width=event.width
            ),
        )

        tk.Label(command_panel, text="Panel RMM Windows", bg="#0B2A5B", fg="#49A7FF",
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22, pady=(18, 18))
        tk.Label(command_panel, text="Seleccion de PC Cliente", bg="#0B2A5B", fg="#FFFFFF",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=22)
        tk.Label(command_panel, text="Sin selección, la acción se aplica a todos",
                 bg="#0B2A5B", fg="#AFC4DD", font=("Segoe UI", 9)).pack(anchor="w", padx=22, pady=(2, 8))

        self.listbox = tk.Listbox(
            command_panel, selectmode="extended", height=5, exportselection=False,
            bg="#FFFFFF", fg="#172B4D", selectbackground="#2563EB",
            selectforeground="#FFFFFF", relief="flat", borderwidth=1,
            highlightthickness=1, highlightbackground="#8EABC9",
            font=("Segoe UI", 10), activestyle="none",
        )
        self.listbox.pack(fill="x", padx=22, pady=(0, 12), ipady=5)

        tk.Label(command_panel, text="Comandos", bg="#0B2A5B", fg="#49A7FF",
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=22, pady=(3, 8))

        def rmm_button(text, command, color="#2D89E5"):
            tk.Button(command_panel, text=text, command=command, bg=color, fg="#FFFFFF",
                      activebackground=color, activeforeground="#FFFFFF",
                      relief="flat", font=("Segoe UI", 10, "bold"),
                      cursor="hand2").pack(fill="x", padx=22, pady=4, ipady=7)

        rmm_button("Ver Cliente 1 y Cliente 2", self.view_all)
        rmm_button("Detener vista", self.stop_dual_view)
        rmm_button(
            "Compartir Cliente 2 → Cliente 1",
            lambda: self.start_client_sharing(2, 1),
        )
        rmm_button(
            "Compartir Cliente 1 → Cliente 2",
            lambda: self.start_client_sharing(1, 2),
        )
        rmm_button("Detener compartir entre clientes", self.stop_client_sharing, "#596B7D")
        rmm_button("Compartir pantalla del servidor", self.start_share)
        rmm_button("Dejar de transmitir pantalla del admin", self.stop_share, "#596B7D")
        rmm_button("Abrir ventana de chat", self.open_chat)
        tk.Label(command_panel, text="Enviar archivo a:", bg="#0B2A5B", fg="#FFFFFF",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=22, pady=(8, 2))
        self.file_recipient = tk.StringVar(value="Cliente 1")
        ttk.Combobox(
            command_panel, textvariable=self.file_recipient,
            values=("Administrador", "Cliente 1", "Cliente 2"),
            state="readonly",
        ).pack(fill="x", padx=22, pady=(0, 4))
        rmm_button("Elegir y enviar archivo", self.send_file)
        rmm_button("6. Bloquear Teclado/Mouse", lambda: self.cmd({"type": "lock"}), "#E6A21A")
        rmm_button("7. Desbloquear Teclado/Mouse", lambda: self.cmd({"type": "unlock"}), "#12AFA8")
        rmm_button("8. Apagar PC Remotamente", self.shutdown, "#E43C46")

        tk.Label(command_panel, text="9. Control Web", bg="#0B2A5B", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=22, pady=(10, 4))
        web_row = tk.Frame(command_panel, bg="#0B2A5B")
        web_row.pack(fill="x", padx=22)
        self.sites = tk.Entry(web_row, bg="#3A5A7A", fg="#FFFFFF",
                              insertbackground="#FFFFFF", relief="flat")
        self.sites.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(web_row, text="Bloquear", command=self.block_sites, bg="#E43C46",
                  fg="#FFFFFF", relief="flat", font=("Segoe UI", 9, "bold")).pack(
                      side="right", padx=(6, 0), ipady=5)
        tk.Label(
            command_panel,
            text="Dominios separados por coma. Vacío al desbloquear = todos.",
            bg="#0B2A5B", fg="#AFC4DD", font=("Segoe UI", 8),
            wraplength=280,
        ).pack(anchor="w", padx=22, pady=(3, 5))
        rmm_button("Desbloquear sitios", self.unblock_sites_selected, "#12AFA8")
        rmm_button("Bloquear en Cliente 1 y 2", self.block_sites_all, "#E43C46")
        rmm_button("Desbloquear en Cliente 1 y 2", self.unblock_sites_all, "#12AFA8")

        tk.Label(command_panel, text="10. Ping de Clientes al Administrador", bg="#0B2A5B", fg="#FFFFFF",
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=22, pady=(8, 4))
        rmm_button("Permitir ping al administrador",
                   lambda: self.set_admin_client_ping(True), "#159447")
        rmm_button("Denegar ping al administrador",
                   lambda: self.set_admin_client_ping(False), "#E43C46")

        right = tk.Frame(content, bg="#0D1B2A")
        right.pack(side="left", fill="both", expand=True)

        monitor = tk.Frame(right, bg="#0D1B2A")
        monitor.pack(fill="both", expand=True, padx=16, pady=16)
        monitor_titles = tk.Frame(monitor, bg="#0D1B2A")
        monitor_titles.pack(fill="x")
        tk.Label(monitor_titles, text="1 & 3. Monitoreo de pantallas",
                 bg="#0D1B2A", fg="#FFFFFF", font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Button(monitor_titles, text="Detener compartir", command=self.stop_share,
                  bg="#243B53", fg="#FFFFFF", relief="flat").pack(side="right")

        screens = tk.Frame(monitor, bg="#0D1B2A")
        screens.pack(fill="both", expand=True, pady=(8, 10))
        for index, title in enumerate(("Cliente 1", "Cliente 2")):
            card = tk.Frame(screens, bg="#1A2A3A", highlightthickness=1,
                            highlightbackground="#314C66")
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 6 if index == 0 else 0),
                      pady=0)
            tk.Label(card, text=title, bg="#1A2A3A", fg="#D7E4F0",
                     font=("Segoe UI", 11, "bold")).pack(pady=(8, 4))
            screen = tk.Label(card, text="Seleccione una PC conectada.",
                              bg="#000000", fg="#66758A", font=("Segoe UI", 12))
            screen.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            screen.bind(
                "<Configure>",
                lambda event, slot=index: self.render_monitor(slot),
            )
            self.monitor_frames[index] = screen
        screens.columnconfigure(0, weight=1)
        screens.columnconfigure(1, weight=1)
        screens.rowconfigure(0, weight=1)

        bottom = tk.Frame(right, bg="#0D1B2A", height=170)
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        bottom.pack_propagate(False)
        log_card = tk.Frame(bottom, bg="#1A2A3A", highlightthickness=1,
                            highlightbackground="#314C66")
        log_card.pack(fill="both", expand=True)
        tk.Label(log_card, text="Actividad del servidor",
                 bg="#1A2A3A", fg="#FFFFFF", font=("Segoe UI", 12, "bold")).pack(pady=6)
        self.log_text = scrolledtext.ScrolledText(log_card, state="disabled", wrap="word",
                                                  bg="#0A1320", fg="#FFFFFF", insertbackground="#FFFFFF",
                                                  relief="flat")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        root.protocol("WM_DELETE_WINDOW", self.quit)
        threading.Thread(target=self.serve, daemon=True).start()
        threading.Thread(target=self.discovery_responder, daemon=True).start()
        self.poll()

    # ---- UI
    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def chat_message(self, text):
        self.chat_history.append(text)
        if self.chat and self.chat.winfo_exists():
            self.chat.configure(state="normal")
            self.chat.insert("end", text + "\n")
            self.chat.see("end")
            self.chat.configure(state="disabled")

    def open_chat(self):
        if self.chat_window and self.chat_window.winfo_exists():
            self.chat_window.deiconify()
            self.chat_window.lift()
            self.chat_entry.focus_set()
            return

        self.chat_window = tk.Toplevel(self.root)
        self.chat_window.title("Chat remoto - Lab Control")
        self.chat_window.geometry("760x620")
        self.chat_window.minsize(560, 420)
        self.chat_window.configure(bg="#0D1B2A")

        panel = tk.Frame(self.chat_window, bg="#1A2A3A")
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(panel, text="Chat remoto con clientes",
                 bg="#1A2A3A", fg="#FFFFFF",
                 font=("Segoe UI", 15, "bold")).pack(pady=(10, 8))
        self.chat = scrolledtext.ScrolledText(
            panel, state="disabled", wrap="word",
            bg="#0A1320", fg="#FFFFFF", insertbackground="#FFFFFF",
            relief="flat", font=("Segoe UI", 11), padx=10, pady=10,
        )
        self.chat.pack(fill="both", expand=True, padx=10)
        self.chat.configure(state="normal")
        self.chat.insert("end", "\n".join(self.chat_history))
        if self.chat_history:
            self.chat.insert("end", "\n")
        self.chat.configure(state="disabled")

        row = tk.Frame(panel, bg="#1A2A3A")
        row.pack(fill="x", padx=10, pady=10)
        self.chat_entry = tk.Entry(
            row, bg="#3A5A7A", fg="#FFFFFF",
            insertbackground="#FFFFFF", relief="flat", font=("Segoe UI", 11),
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.chat_entry.bind("<Return>", lambda event: self.send_chat())
        tk.Button(
            row, text="Enviar", command=self.send_chat, bg="#2D89E5",
            fg="#FFFFFF", relief="flat", font=("Segoe UI", 10, "bold"),
        ).pack(side="right", padx=(8, 0), ipady=7)
        self.chat_window.protocol("WM_DELETE_WINDOW", self.close_chat)
        self.chat_entry.focus_set()

    def close_chat(self):
        if self.chat_window:
            self.chat_window.destroy()
        self.chat_window = None
        self.chat = None
        self.chat_entry = None

    def render_monitor(self, index):
        source = self.monitor_source_images.get(index)
        label = self.monitor_frames.get(index)
        if source is None or label is None or not label.winfo_exists():
            return
        width, height = label.winfo_width() - 12, label.winfo_height() - 12
        if width <= 1 or height <= 1:
            return
        scale = min(width / source.width, height / source.height)
        size = (max(1, int(source.width * scale)), max(1, int(source.height * scale)))
        image = source.resize(size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self.monitor_photos[index] = photo
        label.configure(image=photo, text="")

    def refresh(self):
        self.listbox.delete(0, "end")
        peers = self.ordered_peers()
        peers_by_id = {peer.client_index: peer for peer in peers}
        for client_index in sorted(peers_by_id):
            p = peers_by_id[client_index]
            label = f"Cliente {client_index}: {p.name} ({p.ip})"
            self.listbox.insert("end", label)
        for i in range(2):
            self.monitor_source_images.pop(i, None)
            self.monitor_photos.pop(i, None)
            peer = peers_by_id.get(i + 1)
            if peer:
                text = f"Cliente {i + 1}: {peer.name}\nEsperando pantalla..."
            else:
                text = f"Cliente {i + 1}\nSin PC conectado."
            self.monitor_frames[i].configure(image="", text=text, fg="#66758A")

    def poll(self):
        try:
            while True:
                kind, *a = self.q.get_nowait()
                if kind == "log":
                    self.log(a[0])
                elif kind == "chat":
                    self.chat_message(a[0])
                elif kind == "refresh":
                    self.refresh()
                elif kind == "frame":
                    peer, data = a
                    if peer is self.view_peer and self.viewer and self.viewer.alive:
                        self.viewer.show(data)
                    if self.dual_view:
                        index = peer.client_index - 1
                        with self.peers_lock:
                            is_connected = peer in self.peers
                        if is_connected and 0 <= index < 2:
                            self.monitor_source_images[index] = Image.open(io.BytesIO(data)).copy()
                            self.render_monitor(index)
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def quit(self):
        self.sharing = False
        self.stop_dual_view()
        self.stop_client_sharing()
        self.close_chat()
        self.root.destroy()

    def ordered_peers(self):
        with self.peers_lock:
            return sorted(self.peers, key=lambda peer: peer.client_index)

    def targets(self):
        sel = self.listbox.curselection()
        ordered_peers = self.ordered_peers()
        if sel:
            return [ordered_peers[i] for i in sel if i < len(ordered_peers)]
        return ordered_peers

    def cmd(self, header, payload=b""):
        ts = self.targets()
        if not ts:
            messagebox.showinfo("Aviso", "No hay clientes conectados")
            return
        for p in ts:
            try:
                p.conn.send(header, payload)
            except Exception:
                pass

    # ---- Acciones
    def send_chat(self):
        if not self.chat_entry:
            return
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.broadcast_chat({"type": "chat", "sender": "Administrador", "text": text})
        self.chat_message("Yo: " + text)
        self.chat_entry.delete(0, "end")

    def broadcast_chat(self, header, exclude=None):
        for peer in self.ordered_peers():
            if peer is exclude:
                continue
            try:
                peer.conn.send(header)
            except Exception as exc:
                self.q.put(("log", f"[Error enviando mensaje a Cliente {peer.client_index}] {exc}"))

    def send_file(self):
        recipient = self.file_recipient.get()
        target = None
        if recipient in ("Cliente 1", "Cliente 2"):
            client_index = int(recipient.split()[-1])
            target = next(
                (peer for peer in self.ordered_peers()
                 if peer.client_index == client_index),
                None,
            )
            if target is None:
                messagebox.showinfo("Aviso", f"{recipient} no está conectado")
                return

        path = filedialog.askopenfilename(title=f"Selecciona archivo para {recipient}")
        if not path:
            return

        def work():
            name = os.path.basename(path)
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if recipient == "Administrador":
                    saved_path = save_received(
                        os.path.join(RECV_DIR, "Administrador"), name, data
                    )
                    self.q.put(("log", f"[Archivo guardado para el administrador] {saved_path}"))
                    return
                if target is None:
                    self.q.put(("log", f"[Destinatario no disponible] {recipient}"))
                    return
                target.conn.send({
                    "type": "file",
                    "name": name,
                    "client_index": target.client_index,
                    "sender": "Administrador",
                }, data)
                self.q.put(("log", f"[Archivo enviado a {recipient}] {name}"))
            except Exception as exc:
                self.q.put(("log", f"[Error enviando archivo a {recipient}] {exc}"))
        threading.Thread(target=work, daemon=True).start()

    def shutdown(self):
        if messagebox.askyesno("Confirmar", "¿Apagar Cliente 1 y Cliente 2?"):
            self.cmd_all_clients({"type": "shutdown"})

    def block_sites(self):
        sites = [s.strip() for s in self.sites.get().split(",") if s.strip()]
        if not sites:
            messagebox.showinfo("Aviso", "Escribe al menos un sitio web")
            return
        self.cmd_all_clients({"type": "block_sites", "sites": sites})

    def block_sites_all(self):
        sites = [s.strip() for s in self.sites.get().split(",") if s.strip()]
        if not sites:
            messagebox.showinfo("Aviso", "Escribe al menos un sitio web")
            return
        self.cmd_all_clients({"type": "block_sites", "sites": sites})

    def unblock_sites_selected(self):
        sites = [s.strip() for s in self.sites.get().split(",") if s.strip()]
        self.cmd_all_clients({"type": "unblock_sites", "sites": sites})

    def unblock_sites_all(self):
        sites = [s.strip() for s in self.sites.get().split(",") if s.strip()]
        self.cmd_all_clients({"type": "unblock_sites", "sites": sites})

    def cmd_all_clients(self, header):
        peers_by_id = {
            peer.client_index: peer for peer in self.ordered_peers()
            if peer.client_index in (1, 2)
        }
        if not peers_by_id:
            messagebox.showinfo("Aviso", "No hay clientes conectados")
            return
        for index in (1, 2):
            peer = peers_by_id.get(index)
            if peer is None:
                self.q.put(("log", f"[No conectado] Cliente {index}: no se pudo aplicar la acción"))
                continue
            try:
                peer.conn.send(header)
            except Exception as exc:
                self.q.put(("log", f"[Error con Cliente {index}] {exc}"))

    def set_admin_client_ping(self, allow):
        peers = [
            peer for peer in self.ordered_peers()
            if peer.client_index in (1, 2)
        ]
        if not peers:
            messagebox.showinfo("Aviso", "No hay clientes conectados")
            return

        connected = {peer.client_index for peer in peers}
        for index in (1, 2):
            if index not in connected:
                self.q.put(("log", f"[Aviso] Cliente {index} no está conectado"))

        remote_ips = sorted({peer.ip for peer in peers})

        def work():
            ok, result = set_ping(allow, remote_ips)
            action = "Permitir" if allow else "Denegar"
            prefix = "✔" if ok else "✘"
            self.q.put(("log", f"[{prefix} {action} ping al administrador] {result}"))

        threading.Thread(target=work, daemon=True).start()

    def view_screen(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecciona un cliente de la lista")
            return
        self.stop_view()
        peer = self.ordered_peers()[sel[0]]
        self.view_peer = peer
        self.viewer = Viewer(self.root, f"Pantalla de {peer.name}", on_close=self.stop_view)
        self.watch_screen(peer, "admin-single", True)

    def stop_view(self):
        if self.view_peer:
            self.watch_screen(self.view_peer, "admin-single", False)
        self.view_peer = None
        if self.viewer and self.viewer.alive:
            v, self.viewer = self.viewer, None
            v.on_close = None
            v.close()

    def view_all(self):
        peers_by_id = {peer.client_index: peer for peer in self.ordered_peers()}
        if not peers_by_id:
            messagebox.showinfo("Aviso", "No hay clientes conectados")
            return

        self.stop_dual_view()
        self.dual_view = True
        for index in range(2):
            peer = peers_by_id.get(index + 1)
            if not peer:
                self.monitor_frames[index].configure(
                    text=f"Cliente {index + 1}\nSin PC conectado.",
                    image="",
                    fg="#66758A",
                )
                continue
            try:
                self.watch_screen(peer, "admin-dual", True)
                self.monitor_source_images.pop(index, None)
                self.monitor_photos.pop(index, None)
                self.monitor_frames[index].configure(
                    text=f"Cliente {index + 1}: {peer.name}\nEsperando pantalla...",
                    image="",
                    fg="#66758A",
                )
            except Exception:
                pass

        self.log("[Monitoreando Cliente 1 y Cliente 2]")

    def stop_dual_view(self):
        for peer in self.ordered_peers():
            if peer.client_index not in (1, 2):
                continue
            self.watch_screen(peer, "admin-dual", False)
        self.dual_view = False
        for index in range(2):
            self.monitor_source_images.pop(index, None)
            self.monitor_photos.pop(index, None)
            self.monitor_frames[index].configure(
                image="",
                text=f"Cliente {index + 1}\nVista detenida.",
                fg="#66758A",
            )

    def watch_screen(self, target, watcher, enabled):
        with self.screen_lock:
            watchers = self.screen_watchers.setdefault(target, set())
            was_watched = bool(watchers)
            if enabled:
                watchers.add(watcher)
            else:
                watchers.discard(watcher)
            is_watched = bool(watchers)
            if not is_watched:
                self.screen_watchers.pop(target, None)

        try:
            if enabled and not was_watched:
                target.conn.send({"type": "screen_start"})
            elif not enabled and was_watched and not is_watched:
                target.conn.send({"type": "screen_stop"})
        except Exception as exc:
            self.q.put(("log", f"[Error controlando pantalla de Cliente {target.client_index}] {exc}"))
            with self.screen_lock:
                watchers = self.screen_watchers.get(target)
                if watchers:
                    watchers.discard(watcher)
                    if not watchers:
                        self.screen_watchers.pop(target, None)
            return False
        return True

    def start_client_sharing(self, source_index, recipient_index):
        peers_by_id = {peer.client_index: peer for peer in self.ordered_peers()}
        source = peers_by_id.get(source_index)
        recipient = peers_by_id.get(recipient_index)
        if source is None or recipient is None:
            messagebox.showinfo(
                "Aviso",
                "Cliente 1 y Cliente 2 deben estar conectados para compartir pantalla",
            )
            return

        key = (source_index, recipient_index)
        with self.client_shares_lock:
            if key in self.client_shares:
                return

        try:
            recipient.conn.send({
                "type": "client_screen_start",
                "source_index": source_index,
                "sender": f"Cliente {source_index} ({source.name})",
            })
        except Exception as exc:
            self.q.put(("log", f"[No se pudo avisar a Cliente {recipient_index}] {exc}"))
            return

        if not self.watch_screen(source, recipient, True):
            try:
                recipient.conn.send({
                    "type": "client_screen_stop",
                    "source_index": source_index,
                    "sender": f"Cliente {source_index}",
                })
            except Exception:
                pass
            return
        with self.client_shares_lock:
            self.client_shares[key] = (source, recipient)
        self.q.put((
            "log",
            f"[Compartiendo Cliente {source_index} → Cliente {recipient_index}]",
        ))

    def stop_client_sharing(self):
        with self.client_shares_lock:
            shares = list(self.client_shares.items())
            self.client_shares.clear()
        for (source_index, recipient_index), (source, recipient) in shares:
            try:
                recipient.conn.send({
                    "type": "client_screen_stop",
                    "source_index": source_index,
                    "sender": f"Cliente {source_index}",
                })
            except Exception as exc:
                self.q.put((
                    "log",
                    f"[No se pudo notificar a Cliente {recipient_index}] {exc}",
                ))
            self.watch_screen(source, recipient, False)
        if shares:
            self.q.put(("log", "[Se detuvo el compartir pantalla entre clientes]"))

    def remove_client_shares_for_peer(self, peer):
        with self.client_shares_lock:
            lost_shares = [
                (key, pair) for key, pair in self.client_shares.items()
                if peer in pair
            ]
            for key, _ in lost_shares:
                self.client_shares.pop(key, None)
        for (source_index, recipient_index), (source, recipient) in lost_shares:
            if source is peer and recipient is not peer:
                try:
                    recipient.conn.send({
                        "type": "client_screen_stop",
                        "source_index": source_index,
                        "sender": f"Cliente {source_index}",
                    })
                except Exception:
                    pass
            self.q.put((
                "log",
                f"[Compartir Cliente {source_index} → Cliente {recipient_index} detenido por desconexión]",
            ))

    def remove_screen_watches(self, peer):
        with self.screen_lock:
            watchers = self.screen_watchers.pop(peer, set())
        for watcher in watchers:
            if isinstance(watcher, Peer):
                try:
                    watcher.conn.send({
                        "type": "client_screen_stop",
                        "source_index": peer.client_index,
                        "sender": f"Cliente {peer.client_index}",
                    })
                except Exception:
                    pass
        self.remove_screen_watcher(peer)
        self.remove_client_shares_for_peer(peer)

    def remove_screen_watcher(self, watcher):
        stop_targets = []
        with self.screen_lock:
            for target, watchers in list(self.screen_watchers.items()):
                watchers.discard(watcher)
                if not watchers:
                    self.screen_watchers.pop(target, None)
                    if target is not watcher:
                        stop_targets.append(target)
        for target in stop_targets:
            try:
                target.conn.send({"type": "screen_stop"})
            except Exception:
                self.q.put(("log", f"[No se pudo detener la pantalla de Cliente {target.client_index}]"))

    def start_share(self):
        if self.sharing:
            return
        self.sharing = True
        threading.Thread(target=self.share_loop, daemon=True).start()
        self.log("[Compartiendo tu pantalla con los clientes]")

    def stop_share(self):
        self.sharing = False
        for p in list(self.peers):
            try:
                p.conn.send({"type": "admin_stop"})
            except Exception:
                pass

    def share_loop(self):
        while self.sharing:
            data = capture_jpeg()
            for p in list(self.peers):
                try:
                    p.conn.send({"type": "admin_frame"}, data)
                except Exception:
                    pass
            time.sleep(0.2)

    # ---- Servidor
    def discovery_responder(self):
        """Responde a los clientes que buscan al administrador."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", DISCOVERY_PORT))
        while True:
            try:
                data, addr = s.recvfrom(256)
                if data == DISCOVER_MSG:
                    s.sendto(HERE_MSG, addr)
            except Exception:
                pass

    def serve(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", PORT))
        s.listen(10)
        while True:
            sock, addr = s.accept()
            threading.Thread(target=self.handle, args=(sock, addr), daemon=True).start()

    def handle(self, sock, addr):
        conn = Conn(sock)
        peer = None
        try:
            sock.settimeout(10)
            h, _ = conn.recv()
            password_ok = h.get("type") == "hello" and hmac.compare_digest(
                str(h.get("password", "")).encode(), self.password.encode())
            requested_index = h.get("client_index")
            valid_index = type(requested_index) is int and requested_index in (1, 2)
            with self.peers_lock:
                used_indices = {existing.client_index for existing in self.peers}
                duplicate_index = valid_index and requested_index in used_indices
                ok = password_ok and valid_index and not duplicate_index
                if not password_ok:
                    error = "Contraseña incorrecta"
                elif not valid_index:
                    error = "Selecciona Cliente 1 o Cliente 2"
                elif duplicate_index:
                    error = f"Cliente {requested_index} ya está conectado"
                else:
                    error = ""
                conn.send({
                    "type": "auth",
                    "ok": ok,
                    "error": error,
                    "client_index": requested_index if ok else None,
                })
                if ok:
                    peer = Peer(conn, h.get("name", "PC"), addr[0], requested_index)
                    self.peers.append(peer)
            if not ok:
                conn.close()
                self.q.put(("log", f"[Rechazado {addr[0]}: {error}]"))
                return
            sock.settimeout(None)
        except Exception:
            conn.close()
            if peer:
                with self.peers_lock:
                    if peer in self.peers:
                        self.peers.remove(peer)
            return
        self.q.put(("refresh",))
        self.q.put(("log", f"[Conectado] Cliente {peer.client_index}: {peer.name} ({peer.ip})"))
        try:
            while True:
                hd, payload = conn.recv()
                t = hd.get("type")
                if t == "chat":
                    text = str(hd.get("text", ""))
                    sender = f"Cliente {peer.client_index} ({peer.name})"
                    self.q.put(("chat", f"{sender}: {text}"))
                    self.broadcast_chat(
                        {"type": "chat", "sender": sender, "text": text},
                        exclude=peer,
                    )
                elif t == "frame":
                    self.q.put(("frame", peer, payload))
                    with self.screen_lock:
                        viewers = tuple(self.screen_watchers.get(peer, ()))
                    for viewer in viewers:
                        if isinstance(viewer, Peer):
                            try:
                                viewer.conn.send({
                                    "type": "client_screen_frame",
                                    "source_index": peer.client_index,
                                }, payload)
                            except Exception as exc:
                                self.q.put((
                                    "log",
                                    f"[Error retransmitiendo pantalla de Cliente {peer.client_index} "
                                    f"a Cliente {viewer.client_index}] {exc}",
                                ))
                elif t == "file_send":
                    recipient = hd.get("recipient")
                    name = os.path.basename(str(hd.get("name") or "archivo")) or "archivo"
                    if recipient == "admin":
                        try:
                            folder = os.path.join(
                                RECV_DIR,
                                f"Cliente {peer.client_index} - {os.path.basename(peer.name)}",
                            )
                            path = save_received(folder, name, payload)
                            conn.send({
                                "type": "file_status",
                                "ok": True,
                                "text": f"Archivo recibido por el administrador: {path}",
                            })
                            self.q.put(("log", f"[Archivo de {peer.name}] guardado en {path}"))
                        except Exception as exc:
                            conn.send({
                                "type": "file_status",
                                "ok": False,
                                "text": f"No se pudo guardar en el administrador: {exc}",
                            })
                    elif type(recipient) is int and recipient in (1, 2):
                        target = next(
                            (candidate for candidate in self.ordered_peers()
                             if candidate.client_index == recipient),
                            None,
                        )
                        if target is None:
                            conn.send({
                                "type": "file_status",
                                "ok": False,
                                "text": f"Cliente {recipient} no está conectado",
                            })
                            continue
                        try:
                            target.conn.send({
                                "type": "file",
                                "name": name,
                                "client_index": target.client_index,
                                "sender": f"Cliente {peer.client_index} ({peer.name})",
                            }, payload)
                            conn.send({
                                "type": "file_status",
                                "ok": True,
                                "text": f"Archivo enviado a Cliente {recipient}",
                            })
                            self.q.put((
                                "log",
                                f"[Archivo de Cliente {peer.client_index} enviado a Cliente {recipient}] {name}",
                            ))
                        except Exception as exc:
                            conn.send({
                                "type": "file_status",
                                "ok": False,
                                "text": f"No se pudo enviar a Cliente {recipient}: {exc}",
                            })
                    else:
                        conn.send({
                            "type": "file_status",
                            "ok": False,
                            "text": "Destinatario de archivo no válido",
                        })
                elif t == "file":
                    path = save_received(os.path.join(RECV_DIR, peer.name), hd.get("name", "archivo"), payload)
                    self.q.put(("log", f"[Archivo de {peer.name}] guardado en {path}"))
                elif t == "status":
                    self.q.put(("log", f"{peer.name}: {hd.get('text', '')}"))
        except Exception:
            pass
        conn.close()
        self.remove_screen_watches(peer)
        with self.peers_lock:
            if peer in self.peers:
                self.peers.remove(peer)
        self.q.put(("refresh",))
        self.q.put(("log", f"[Desconectado] {peer.name}"))
