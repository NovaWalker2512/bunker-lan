import tkinter as tk
from tkinter import ttk


def create_app() -> tk.Tk:
    """Create and configure the main application window."""
    root = tk.Tk()
    root.title("Bunker LAN")
    root.geometry("800x500")
    root.minsize(640, 400)

    container = ttk.Frame(root, padding=24)
    container.pack(fill="both", expand=True)

    title = ttk.Label(
        container,
        text="Bunker LAN",
        font=("Segoe UI", 22, "bold"),
    )
    title.pack(pady=(0, 12))

    subtitle = ttk.Label(
        container,
        text="Локальная многопользовательская игра",
    )
    subtitle.pack()

    status = ttk.Label(
        container,
        text="Этап 1: подготовка приложения",
    )
    status.pack(pady=16)

    return root
