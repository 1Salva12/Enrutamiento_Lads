#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Client application for Lab Control."""
import os
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from comun import (
    PORT, Conn, Viewer, block_sites, capture_jpeg, discover_admin,
    received_dir_for_client, save_received, set_input_lock, set_ping,
    setup_theme, shutdown_pc, style_text_widget, unblock_sites,
)

class ClientApp:
    def __init__(self, root, host, password, client_index=1):
        self.root, self.host, self.password = root, host, password
        self.client_index = client_index
        self.conn = None
        self.q = queue.Queue()
        self.streaming = False
        self.viewer = None
        self.peer_viewers = {}
        self.locked = False
        for w in root.winfo_children():
            w.destroy()
        setup_theme(root)
        root.title("Lab Control - CLIENTE")
        root.geometry("700x600")
        root.minsize(560, 480)

        header = ttk.Frame(root, style="Header.TFrame", padding=(24, 18))
        header.pack(fill="x")
        title_area = ttk.Frame(header, style="Header.TFrame")
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="Lab Control", style="Header.TLabel",
                  font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(title_area, text="Consola del equipo cliente",
                  style="Header.TLabel", foreground="#C8D5E6").pack(anchor="w", pady=(3, 0))
        self.status = ttk.Label(header, text="● Conectando...", style="Header.TLabel",
                                font=("Segoe UI", 10, "bold"))
        self.status.pack(side="right", padx=(12, 0))

        body = ttk.Frame(root, padding=20)
        body.pack(fill="both", expand=True)
        notice = ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
        notice.pack(fill="x", pady=(0, 14))
        ttk.Label(notice, text="Este equipo puede ser administrado a distancia.",
                  style="Card.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(notice, text="Cierra esta ventana para desconectarte.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 0))

        chat_card = ttk.Frame(body, style="Card.TFrame", padding=12)
        chat_card.pack(fill="both", expand=True)
        ttk.Label(chat_card, text="Mensajes y actividad", style="Card.TLabel",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        self.chat = scrolledtext.ScrolledText(chat_card, height=15, state="disabled", wrap="word")
        style_text_widget(self.chat)
        self.chat.pack(fill="both", expand=True)
        row = ttk.Frame(chat_card, style="Card.TFrame")
        row.pack(fill="x", pady=(10, 0))
        self.entry = ttk.Entry(row)
        self.entry.pack(side="left", fill="x", expand=True, ipady=2)
        self.entry.bind("<Return>", lambda e: self.send_chat())
        ttk.Button(row, text="Enviar", command=self.send_chat,
                   style="Primary.TButton").pack(side="right")
        file_row = ttk.Frame(row, style="Card.TFrame")
        file_row.pack(side="right", padx=(8, 0))
        ttk.Label(file_row, text="Destinatario:", style="Card.TLabel").pack(side="left")
        self.file_recipient = tk.StringVar(value="Administrador")
        ttk.Combobox(
            file_row, textvariable=self.file_recipient,
            values=("Administrador", "Cliente 1", "Cliente 2"),
            state="readonly", width=13,
        ).pack(side="left", padx=4)
        ttk.Button(file_row, text="Archivo", command=self.send_file).pack(side="left")
        root.protocol("WM_DELETE_WINDOW", self.quit)
        threading.Thread(target=self.connect_loop, daemon=True).start()
        self.poll()

    # ---- UI
    def log(self, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", text + "\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, *args = self.q.get_nowait()
                if kind == "chat":
                    self.log(args[0])
                elif kind == "status":
                    self.status.configure(text=args[0], foreground=args[1])
                elif kind == "admin_frame":
                    if not self.viewer or not self.viewer.alive:
                        self.viewer = Viewer(self.root, "Pantalla del administrador")
                    self.viewer.show(args[0])
                elif kind == "client_screen_start":
                    source_index, sender = args
                    viewer = self.peer_viewers.get(source_index)
                    if not viewer or not viewer.alive:
                        viewer = Viewer(self.root, f"Pantalla de {sender}")
                        self.peer_viewers[source_index] = viewer
                    self.log(f"[El administrador compartió la pantalla de {sender}]")
                elif kind == "client_screen_frame":
                    source_index, data = args
                    viewer = self.peer_viewers.get(source_index)
                    if viewer and viewer.alive:
                        viewer.show(data)
                elif kind == "client_screen_stop":
                    source_index, sender = args
                    viewer = self.peer_viewers.pop(source_index, None)
                    if viewer and viewer.alive:
                        viewer.close()
                    self.log(f"[Se detuvo la pantalla compartida de {sender}]")
                elif kind == "admin_stop":
                    if self.viewer:
                        self.viewer.close()
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def quit(self):
        self.streaming = False
        set_input_lock(False)
        if self.conn:
            self.conn.close()
        self.root.destroy()

    # ---- Red
    def connect_loop(self):
        manual = bool(self.host)
        while True:
            try:
                if not manual:
                    self.q.put(("status", "Buscando administrador en la red...", "orange"))
                    found = discover_admin()
                    if not found:
                        continue
                    self.host = found
                s = socket.create_connection((self.host, PORT), timeout=8)
                s.settimeout(None)
                self.conn = Conn(s)
                self.conn.send({
                    "type": "hello",
                    "name": socket.gethostname(),
                    "password": self.password,
                    "client_index": self.client_index,
                })
                h, _ = self.conn.recv()
                if not h.get("ok"):
                    self.q.put(("status", h.get("error", "Conexión rechazada"), "red"))
                    return
                self.client_index = h.get("client_index", self.client_index)
                self.q.put(("status", f"Conectado a {self.host}", "green"))
                self.listen()
            except Exception:
                pass
            self.streaming = False
            if self.locked:
                set_input_lock(False)
                self.locked = False
            self.q.put(("status", "Desconectado. Reintentando...", "orange"))
            time.sleep(3)

    def report(self, ok_msg):
        ok, msg = ok_msg
        try:
            self.conn.send({"type": "status", "text": ("✔ " if ok else "✘ ") + msg})
        except Exception:
            pass

    def listen(self):
        while True:
            h, p = self.conn.recv()
            t = h.get("type")
            if t == "chat":
                sender = h.get("sender", "Administrador")
                self.q.put(("chat", f"{sender}: {h.get('text', '')}"))
            elif t == "client_screen_start":
                source_index = h.get("source_index")
                if type(source_index) is int and source_index in (1, 2):
                    self.q.put((
                        "client_screen_start",
                        source_index,
                        h.get("sender", f"Cliente {source_index}"),
                    ))
            elif t == "client_screen_frame":
                source_index = h.get("source_index")
                if type(source_index) is int and source_index in (1, 2):
                    self.q.put(("client_screen_frame", source_index, p))
            elif t == "client_screen_stop":
                source_index = h.get("source_index")
                if type(source_index) is int and source_index in (1, 2):
                    self.q.put((
                        "client_screen_stop",
                        source_index,
                        h.get("sender", f"Cliente {source_index}"),
                    ))
            elif t == "file":
                sender = h.get("sender", "Administrador")
                try:
                    folder = received_dir_for_client(
                        h.get("client_index", self.client_index)
                    )
                    path = save_received(folder, h.get("name", "archivo"), p)
                except Exception as exc:
                    self.q.put(("chat", f"[Error recibiendo archivo de {sender}] {exc}"))
                    self.report((False, f"Error guardando archivo: {exc}"))
                else:
                    self.q.put(("chat", f"[Archivo recibido de {sender}] {path}"))
                    self.report((True, f"Archivo guardado en {path}"))
            elif t == "file_status":
                prefix = "✔" if h.get("ok") else "✘"
                self.q.put(("chat", f"[{prefix} {h.get('text', 'Estado de envío desconocido')}]"))
            elif t == "screen_start" and not self.streaming:
                self.streaming = True
                threading.Thread(target=self.stream, daemon=True).start()
            elif t == "screen_stop":
                self.streaming = False
            elif t == "lock":
                r = set_input_lock(True)
                self.locked = r[0]
                self.q.put(("status", "Teclado/mouse BLOQUEADOS" if r[0] else "Conectado", "red" if r[0] else "green"))
                self.report(r)
            elif t == "unlock":
                r = set_input_lock(False)
                self.locked = False
                self.q.put(("status", f"Conectado a {self.host}", "green"))
                self.report(r)
            elif t == "shutdown":
                ok, result = shutdown_pc()
                if ok:
                    self.report((True, result or "Apagado programado"))
                else:
                    self.report((False, result))
            elif t == "block_sites":
                self.report(block_sites(h.get("sites", [])))
            elif t == "unblock_sites":
                self.report(unblock_sites(h.get("sites")))
            elif t == "ping_block":
                self.report(set_ping(False))
            elif t == "ping_allow":
                self.report(set_ping(True))
            elif t == "admin_frame":
                self.q.put(("admin_frame", p))
            elif t == "admin_stop":
                self.q.put(("admin_stop",))

    def stream(self):
        while self.streaming:
            try:
                self.conn.send({"type": "frame"}, capture_jpeg())
            except Exception:
                break
            time.sleep(0.15)
        self.streaming = False

    def send_chat(self):
        text = self.entry.get().strip()
        if text and self.conn:
            try:
                self.conn.send({"type": "chat", "text": text})
                self.log("Yo: " + text)
                self.entry.delete(0, "end")
            except Exception:
                self.log("[Sin conexión]")

    def send_file(self):
        conn = self.conn
        if not conn:
            self.log("[Sin conexión al administrador]")
            return
        recipient = self.file_recipient.get()
        recipient_id = {
            "Administrador": "admin",
            "Cliente 1": 1,
            "Cliente 2": 2,
        }.get(recipient)
        if recipient_id is None:
            self.log("[Selecciona un destinatario válido]")
            return
        path = filedialog.askopenfilename(title=f"Selecciona archivo para {recipient}")
        if not path:
            return

        def work():
            try:
                with open(path, "rb") as f:
                    data = f.read()
                conn.send({
                    "type": "file_send",
                    "recipient": recipient_id,
                    "name": os.path.basename(path),
                }, data)
                self.q.put(("chat", f"[Enviando archivo a {recipient}] {os.path.basename(path)}"))
            except Exception as e:
                self.q.put(("chat", f"[Error enviando archivo a {recipient}] {e}"))
        threading.Thread(target=work, daemon=True).start()
