
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from bunker.network.client import BunkerClient
from bunker.network.server import BunkerServer


class BunkerApplication(tk.Tk):
    """Графическое приложение игры «Бункер LAN»."""

    def __init__(self) -> None:
        """Создаёт окно приложения и начальный экран."""
        super().__init__()

        self.title("Бункер LAN")
        self.geometry("800x600")
        self.minsize(650, 500)

        self.client: BunkerClient | None = None
        self.server: BunkerServer | None = None

        self.player_id: str | None = None
        self.host_id: str | None = None
        self.players: list[dict] = []

        self.is_host = False
        self.room_port = 5000
        self.connecting = False
        self.connect_buttons: list[ttk.Button] = []

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show_home()

    def _clear_screen(self) -> None:
        """Удаляет виджеты текущего экрана."""
        for widget in self.winfo_children():
            widget.destroy()

    def _show_home(self) -> None:
        """Создаёт экран создания комнаты и подключения."""
        self._clear_screen()
        self.connect_buttons = []

        frame = ttk.Frame(self, padding=30)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Бункер LAN",
            font=("Segoe UI", 24, "bold"),
        ).pack(pady=(10, 5))

        ttk.Label(
            frame,
            text="Кооперативная игра по локальной сети",
        ).pack(pady=(0, 25))

        form = ttk.Frame(frame)
        form.pack(fill="x", padx=30)

        ttk.Label(form, text="Твой никнейм:").grid(
            row=0, column=0, sticky="w", pady=8
        )
        self.nickname_entry = ttk.Entry(form)
        self.nickname_entry.insert(0, "Игрок")
        self.nickname_entry.grid(
            row=0, column=1, sticky="ew", pady=8
        )

        ttk.Label(form, text="IP-адрес ведущего:").grid(
            row=1, column=0, sticky="w", pady=8
        )
        self.host_entry = ttk.Entry(form)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.grid(
            row=1, column=1, sticky="ew", pady=8
        )

        ttk.Label(form, text="Порт:").grid(
            row=2, column=0, sticky="w", pady=8
        )
        self.port_entry = ttk.Entry(form)
        self.port_entry.insert(0, "5000")
        self.port_entry.grid(
            row=2, column=1, sticky="ew", pady=8
        )

        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", padx=30, pady=20)

        create_button = ttk.Button(
            buttons,
            text="Создать комнату",
            command=self._create_room,
        )
        create_button.pack(fill="x", pady=5)

        join_button = ttk.Button(
            buttons,
            text="Подключиться к комнате",
            command=self._join_room,
        )
        join_button.pack(fill="x", pady=5)

        self.connect_buttons = [create_button, join_button]

        ttk.Label(
            frame,
            text=(
                "Для проверки на одном компьютере используй "
                "адрес 127.0.0.1. Для подключения через Wi-Fi "
                "укажи IPv4-адрес компьютера ведущего."
            ),
            wraplength=650,
            justify="center",
        ).pack(pady=10)

    def _read_form(self) -> tuple[str, int] | None:
        """Проверяет никнейм и порт из формы.

        Returns:
            Пара из никнейма и порта или None при ошибке.
        """
        nickname = self.nickname_entry.get().strip()

        if not nickname or len(nickname) > 20:
            messagebox.showerror(
                "Ошибка",
                "Никнейм должен содержать от 1 до 20 символов.",
            )
            return None

        try:
            port = int(self.port_entry.get())
        except ValueError:
            messagebox.showerror(
                "Ошибка",
                "Порт должен быть целым числом.",
            )
            return None

        if not 1 <= port <= 65535:
            messagebox.showerror(
                "Ошибка",
                "Порт должен быть от 1 до 65535.",
            )
            return None

        return nickname, port

    def _create_room(self) -> None:
        """Запускает сервер и подключает ведущего к комнате."""
        form_data = self._read_form()

        if form_data is None:
            return

        nickname, port = form_data

        self._begin_connection(
            host="127.0.0.1",
            port=port,
            nickname=nickname,
            create_server=True,
        )

    def _join_room(self) -> None:
        """Подключается к комнате на указанном компьютере."""
        form_data = self._read_form()

        if form_data is None:
            return

        nickname, port = form_data
        host = self.host_entry.get().strip()

        if not host:
            messagebox.showerror(
                "Ошибка",
                "Укажи IP-адрес ведущего.",
            )
            return

        self._begin_connection(
            host=host,
            port=port,
            nickname=nickname,
            create_server=False,
        )

    def _begin_connection(
        self,
        host: str,
        port: int,
        nickname: str,
        create_server: bool,
    ) -> None:
        """Запускает подключение в отдельном потоке.

        Args:
            host: Адрес сервера для подключения.
            port: Порт игровой комнаты.
            nickname: Никнейм игрока.
            create_server: Нужно ли запустить сервер на этом ПК.
        """
        if self.connecting:
            return

        self.connecting = True

        for button in self.connect_buttons:
            button.configure(state="disabled")

        threading.Thread(
            target=self._connection_worker,
            args=(host, port, nickname, create_server),
            daemon=True,
        ).start()

    def _connection_worker(
        self,
        host: str,
        port: int,
        nickname: str,
        create_server: bool,
    ) -> None:
        """Устанавливает соединение вне главного потока интерфейса.

        Args:
            host: Адрес сервера.
            port: Порт комнаты.
            nickname: Никнейм игрока.
            create_server: Нужно ли запускать сервер.
        """
        server = None
        client = BunkerClient()

        try:
            if create_server:
                server = BunkerServer(
                    host="0.0.0.0",
                    port=port,
                )
                server.start()

                host = "127.0.0.1"

            client.connect(host, port)
            client.send(
                {
                    "type": "join",
                    "nickname": nickname,
                }
            )

        except (OSError, RuntimeError, ValueError) as exc:
            error_message = str(exc)
            client.close()

            if server is not None:
                server.stop()

            self.after(
                0,
                lambda message=error_message:
                self._connection_failed(message),
            )
            return

        self.after(
            0,
            lambda: self._connection_succeeded(
                client,
                server,
                create_server,
                port,
            ),
        )

    def _connection_failed(self, message: str) -> None:
        """Возвращает пользователя на начальный экран при ошибке.

        Args:
            message: Текст ошибки подключения.
        """
        self.connecting = False
        self._show_home()

        messagebox.showerror(
            "Не удалось подключиться",
            message,
        )

    def _connection_succeeded(
        self,
        client: BunkerClient,
        server: BunkerServer | None,
        is_host: bool,
        port: int,
    ) -> None:
        """Сохраняет соединение и открывает комнату ожидания.

        Args:
            client: Подключённый сетевой клиент.
            server: Сервер, если пользователь создал комнату.
            is_host: Является ли пользователь ведущим.
            port: Порт игровой комнаты.
        """
        self.connecting = False
        self.client = client
        self.server = server
        self.is_host = is_host
        self.room_port = port

        self.player_id = None
        self.host_id = None
        self.players = []

        self._show_lobby()
        self.after(100, self._poll_messages)

    def _show_lobby(self) -> None:
        """Создаёт экран комнаты ожидания."""
        self._clear_screen()

        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Комната ожидания",
            font=("Segoe UI", 20, "bold"),
        ).pack(pady=(0, 10))

        if self.is_host:
            info = (
                f"Сервер запущен на порту {self.room_port}. "
                "Для подключения других компьютеров узнай "
                "IPv4-адрес этого ПК командой ipconfig."
            )
        else:
            info = "Ты подключён к игровой комнате."

        ttk.Label(
            frame,
            text=info,
            wraplength=700,
            justify="center",
        ).pack(pady=(0, 15))

        self.status_label = ttk.Label(
            frame,
            text="Получаем состояние комнаты...",
        )
        self.status_label.pack(pady=5)

        self.players_list = tk.Listbox(
            frame,
            height=10,
            font=("Segoe UI", 12),
            activestyle="none",
        )
        self.players_list.pack(fill="both", expand=True, pady=10)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=10)

        self.ready_button = ttk.Button(
            controls,
            text="Готов",
            command=self._toggle_ready,
            state="disabled",
        )
        self.ready_button.pack(side="left", expand=True, fill="x", padx=4)

        self.start_button = ttk.Button(
            controls,
            text="Начать игру",
            command=self._start_game,
            state="disabled",
        )
        self.start_button.pack(side="left", expand=True, fill="x", padx=4)

        ttk.Button(
            controls,
            text="Покинуть комнату",
            command=self._leave_room,
        ).pack(side="left", expand=True, fill="x", padx=4)

    def _poll_messages(self) -> None:
        """Читает сообщения клиента без блокировки окна."""
        client = self.client

        if client is None:
            return

        while True:
            try:
                message = client.receive(timeout=0)
            except queue.Empty:
                break

            self._handle_message(message)

            if self.client is None:
                return

        self.after(100, self._poll_messages)

    def _handle_message(self, message: dict) -> None:
        """Обрабатывает сообщения сервера.

        Args:
            message: Полученное сетевое сообщение.
        """
        message_type = message.get("type")

        if message_type == "welcome":
            self.player_id = message.get("player_id")
            return

        if message_type == "lobby_state":
            self.players = message.get("players", [])
            self.host_id = message.get("host_id")
            self._update_lobby(message)
            return

        if message_type == "error":
            messagebox.showerror(
                "Ошибка комнаты",
                message.get("message", "Неизвестная ошибка."),
            )
            return

        if message_type == "disconnected":
            reason = message.get(
                "message",
                "Соединение с сервером потеряно.",
            )
            self._disconnect(show_home=True)
            messagebox.showerror("Связь потеряна", reason)

    def _update_lobby(self, state: dict) -> None:
        """Обновляет список игроков и состояние кнопок.

        Args:
            state: Текущее состояние комнаты с сервера.
        """
        self.players_list.delete(0, tk.END)

        for player in self.players:
            role = " (ведущий)" if player["is_host"] else ""
            readiness = "готов" if player["ready"] else "не готов"

            self.players_list.insert(
                tk.END,
                f'{player["nickname"]}{role} — {readiness}',
            )

        ready_count = sum(
            player["ready"] for player in self.players
        )

        if state["started"]:
            status = "Партия началась!"
        else:
            status = (
                f'Игроков: {len(self.players)}/{state["max_players"]}. '
                f"Готовы: {ready_count}/{len(self.players)}. "
                f'Для старта нужно минимум {state["min_players"]}.'
            )

        self.status_label.configure(text=status)

        own_player = next(
            (
                player
                for player in self.players
                if player["player_id"] == self.player_id
            ),
            None,
        )

        if own_player is not None:
            button_text = (
                "Снять готовность"
                if own_player["ready"]
                else "Готов"
            )
            self.ready_button.configure(
                text=button_text,
                state="disabled" if state["started"] else "normal",
            )

        can_start = (
            self.player_id == self.host_id
            and not state["started"]
            and len(self.players) >= state["min_players"]
            and all(player["ready"] for player in self.players)
        )

        self.start_button.configure(
            state="normal" if can_start else "disabled"
        )

    def _toggle_ready(self) -> None:
        """Переключает готовность текущего игрока."""
        if self.client is None or self.player_id is None:
            return

        own_player = next(
            (
                player
                for player in self.players
                if player["player_id"] == self.player_id
            ),
            None,
        )

        if own_player is None:
            return

        try:
            self.client.send(
                {
                    "type": "ready",
                    "ready": not own_player["ready"],
                }
            )
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Ошибка отправки", str(exc))

    def _start_game(self) -> None:
        """Отправляет серверу запрос на начало партии."""
        if self.client is None:
            return

        try:
            self.client.send({"type": "start"})
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Ошибка отправки", str(exc))

    def _leave_room(self) -> None:
        """Закрывает соединение и возвращает пользователя в меню."""
        self._disconnect(show_home=True)

    def _disconnect(self, show_home: bool) -> None:
        """Закрывает клиент и локальный сервер, если он был запущен.

        Args:
            show_home: Нужно ли вернуться на начальный экран.
        """
        client = self.client
        server = self.server

        self.client = None
        self.server = None
        self.player_id = None
        self.host_id = None
        self.players = []

        if client is not None:
            client.close()

        if server is not None:
            server.stop()

        if show_home:
            self._show_home()

    def _on_close(self) -> None:
        """Корректно закрывает сетевые соединения и окно."""
        self._disconnect(show_home=False)
        self.destroy()


def create_app() -> BunkerApplication:
    """Создаёт экземпляр графического приложения.

    Returns:
        Главное окно игры «Бункер LAN».
    """
    return BunkerApplication()
