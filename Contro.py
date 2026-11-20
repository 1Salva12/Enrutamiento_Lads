#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lab Control launcher. Client and administrator code live in separate modules."""
import tkinter as tk
from tkinter import messagebox, ttk

from administrador import AdminApp
from cliente import ClientApp
from comun import COLORS, setup_theme

def main():
    root = tk.Tk()
    setup_theme(root)
    root.title("Lab Control")
    root.geometry("560x690")
    root.minsize(500, 640)
    role = tk.StringVar(value="cliente")
    header = ttk.Frame(root, style="Header.TFrame", padding=(28, 24))
    header.pack(fill="x")
    ttk.Label(header, text="Lab Control", style="Header.TLabel",
              font=("Segoe UI", 23, "bold")).pack(anchor="w")
    ttk.Label(header, text="Administración sencilla para tu laboratorio",
              style="Header.TLabel", foreground="#C8D5E6").pack(anchor="w", pady=(5, 0))

    body = ttk.Frame(root, padding=24)
    body.pack(fill="both", expand=True)
    card = ttk.Frame(body, style="Card.TFrame", padding=20)
    card.pack(fill="both", expand=True)
    ttk.Label(card, text="Configura tu conexión", style="Card.TLabel",
              font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(card, text="Elige el rol de este equipo para continuar.",
              style="Muted.TLabel").pack(anchor="w", pady=(4, 14))

    roles = ttk.Frame(card, style="Card.TFrame")
    roles.pack(fill="x", pady=(0, 14))
    ttk.Radiobutton(roles, text="Cliente", variable=role, value="cliente").pack(
        side="left", fill="x", expand=True, padx=(0, 6), ipady=9
    )
    ttk.Radiobutton(roles, text="Administrador", variable=role, value="admin").pack(
        side="left", fill="x", expand=True, padx=(6, 0), ipady=9
    )

    ttk.Label(card, text="IP del administrador (opcional)", style="Card.TLabel",
              font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Label(card, text="Déjala vacía para detectar al administrador automáticamente.",
              style="Muted.TLabel", wraplength=420).pack(anchor="w", pady=(3, 6))
    ip_e = ttk.Entry(card)
    ip_e.pack(fill="x", pady=(0, 14), ipady=2)
    ttk.Label(card, text="Número de cliente (elige 1 o 2 en cada PC cliente)",
              style="Card.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    client_index = tk.StringVar(value="1")
    ttk.Combobox(card, textvariable=client_index, values=("1", "2"),
                 state="readonly").pack(fill="x", pady=(6, 14), ipady=2)
    ttk.Label(card, text="Contraseña compartida", style="Card.TLabel",
              font=("Segoe UI", 10, "bold")).pack(anchor="w")
    pw_e = ttk.Entry(card, show="*")
    pw_e.pack(fill="x", pady=(6, 16), ipady=2)

    def start():
        pw = pw_e.get()
        if not pw:
            messagebox.showerror("Error", "Escribe una contraseña")
            return
        if role.get() == "admin":
            AdminApp(root, pw)
        else:
            ClientApp(root, ip_e.get().strip(), pw, int(client_index.get()))

    ttk.Button(card, text="Iniciar Lab Control", command=start,
               style="Primary.TButton").pack(fill="x", pady=(0, 5))
    ttk.Label(body, text="Conecta los equipos a la misma red para comenzar.",
              foreground=COLORS["muted"]).pack(anchor="center", pady=(12, 0))
    root.mainloop()


if __name__ == "__main__":
    main()
