import tkinter as tk
import threading
import time
import urllib.request
import json
import sys

# ── Configuración ──────────────────────────────────────────────────────────────
API_URL      = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
REFRESH_SEC  = 30

# ── Tamaños ────────────────────────────────────────────────────────────────────
W_START, H_START = 280, 140
W_MIN,   H_MIN   = 240,  54   # mínimo: solo el precio + bordes/padding
W_MAX,   H_MAX   = W_START, H_START

# Umbrales de altura para ocultar filas (de abajo hacia arriba)
H_HIDE_STATUS = 118
H_HIDE_24H    =  96
H_HIDE_TITLE  =  74

# ── Paleta retro naranja ───────────────────────────────────────────────────────
BG_COLOR     = "#0D0D0D"
BORDER_COLOR = "#FF6600"
PRICE_COLOR  = "#FF8C00"
LABEL_COLOR  = "#FF4500"
CHANGE_POS   = "#00FF66"
CHANGE_NEG   = "#FF3333"
DIM_COLOR    = "#4A2000"
FONT_MONO    = ("Courier New", 10, "bold")
FONT_PRICE   = ("Courier New", 22, "bold")
FONT_TITLE   = ("Courier New",  9, "bold")
FONT_SMALL   = ("Courier New",  8)


class BTCWidget:
    def __init__(self, root: tk.Tk):
        self.root      = root
        self._drag_x   = 0
        self._drag_y   = 0
        self._resize_x = 0
        self._resize_y = 0

        self._build_window()
        self._build_ui()
        self._start_fetch_loop()

    # ── Ventana ────────────────────────────────────────────────────────────────
    def _build_window(self):
        self.root.title("BTC Widget")
        self.root.overrideredirect(True)
        self._topmost = True
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg=BG_COLOR)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - W_START - 30
        y  = sh - H_START - 60
        self.root.geometry(f"{W_START}x{H_START}+{x}+{y}")

        self.menu = tk.Menu(self.root, tearoff=0,
                            bg="#1A0A00", fg=BORDER_COLOR,
                            activebackground=BORDER_COLOR,
                            activeforeground=BG_COLOR,
                            font=FONT_MONO)
        self.menu.add_command(label="  Actualizar ahora",   command=self._fetch_price_once)
        self.menu.add_separator()
        self.menu.add_command(label="  Siempre encima: ON", command=self._toggle_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="  Cerrar",             command=self.root.destroy)
        self.root.bind("<Button-3>", self._show_menu)

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.outer = tk.Frame(self.root, bg=BORDER_COLOR, padx=2, pady=2)
        self.outer.pack(fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(self.outer, bg=BG_COLOR, padx=10, pady=8)
        self.inner.pack(fill=tk.BOTH, expand=True)

        # ── Fila superior: título + indicador ──
        self.frame_top = tk.Frame(self.inner, bg=BG_COLOR)
        self.frame_top.pack(fill=tk.X)

        tk.Label(self.frame_top, text="▶ BTC/USD LIVE", bg=BG_COLOR,
                 fg=LABEL_COLOR, font=FONT_TITLE).pack(side=tk.LEFT)

        self.dot = tk.Label(self.frame_top, text="●", bg=BG_COLOR,
                            fg=DIM_COLOR, font=FONT_SMALL)
        self.dot.pack(side=tk.RIGHT)

        # ── Separador ──
        self.frame_sep = tk.Frame(self.inner, bg=BORDER_COLOR, height=1)
        self.frame_sep.pack(fill=tk.X, pady=(4, 0))

        # ── Precio principal (siempre visible) ──
        self.price_row = tk.Frame(self.inner, bg=BG_COLOR)
        self.price_row.pack(fill=tk.X, pady=(6, 0))

        self.lbl_dollar = tk.Label(self.price_row, text="$", bg=BG_COLOR,
                                   fg=PRICE_COLOR, font=FONT_PRICE,
                                   cursor="hand2")
        self.lbl_dollar.pack(side=tk.LEFT)
        self.lbl_dollar.bind("<Button-1>", self._reset_size)

        self.lbl_price = tk.Label(self.price_row, text=" ───────",
                                  bg=BG_COLOR, fg=PRICE_COLOR,
                                  font=FONT_PRICE, anchor="w")
        self.lbl_price.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Variación 24 h ──
        self.frame_bot = tk.Frame(self.inner, bg=BG_COLOR)
        self.frame_bot.pack(fill=tk.X, pady=(2, 0))

        tk.Label(self.frame_bot, text="24h:", bg=BG_COLOR, fg="#FFFFFF",
                 font=FONT_SMALL).pack(side=tk.LEFT)

        self.lbl_change = tk.Label(self.frame_bot, text="  ─────",
                                   bg=BG_COLOR, fg=DIM_COLOR, font=FONT_MONO)
        self.lbl_change.pack(side=tk.LEFT, padx=(4, 0))

        # ── Estado / hora ──
        self.lbl_status = tk.Label(self.inner, text="",
                                   bg=BG_COLOR, fg=DIM_COLOR,
                                   font=("Courier New", 7))
        self.lbl_status.pack(fill=tk.X, pady=(4, 0))

        # ── Grip de redimensión: flota sobre la esquina del borde naranja ──
        self.grip = tk.Label(self.root, text="◢", bg=BORDER_COLOR,
                             fg=BG_COLOR, font=("Courier New", 9),
                             cursor="sizing")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")

        # Bindings para mover el widget
        for w in (self.root, self.outer, self.inner,
                  self.price_row, self.frame_top, self.frame_sep):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>",     self._on_drag_move)

        # Bindings para redimensionar
        self.grip.bind("<ButtonPress-1>", self._on_resize_start)
        self.grip.bind("<B1-Motion>",     self._on_resize_move)

    # ── Arrastre / mover ──────────────────────────────────────────────────────
    def _on_drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_move(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        self.root.geometry(f"+{self.root.winfo_x()+dx}+{self.root.winfo_y()+dy}")

    # ── Redimensionar ─────────────────────────────────────────────────────────
    def _on_resize_start(self, event):
        self._resize_x = event.x_root
        self._resize_y = event.y_root
        return "break"

    def _on_resize_move(self, event):
        dx = event.x_root - self._resize_x
        dy = event.y_root - self._resize_y
        self._resize_x = event.x_root
        self._resize_y = event.y_root

        nw = max(W_MIN, min(W_MAX, self.root.winfo_width()  + dx))
        nh = max(H_MIN, min(H_MAX, self.root.winfo_height() + dy))
        self.root.geometry(f"{nw}x{nh}")
        self._apply_layout(nh)
        return "break"

    def _reset_size(self, event=None):
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{W_START}x{H_START}+{x}+{y}")
        self._apply_layout(H_START)
        return "break"

    def _apply_layout(self, h: int):
        """Oculta/muestra filas respetando siempre el orden de pack."""
        # 1. Quitar todos los elementos colapsables del layout
        for w in (self.frame_top, self.frame_sep, self.frame_bot, self.lbl_status):
            w.pack_forget()

        # 2. Re-insertar en el orden correcto según la altura actual.
        #    Los elementos de ARRIBA del precio usan before= para garantizar posición.
        if h > H_HIDE_TITLE:
            self.frame_top.pack(fill=tk.X,           before=self.price_row)
            self.frame_sep.pack(fill=tk.X, pady=(4, 0), before=self.price_row)

        # 3. Elementos de ABAJO del precio se agregan después (orden natural)
        if h > H_HIDE_24H:
            self.frame_bot.pack(fill=tk.X, pady=(2, 0))

        if h > H_HIDE_STATUS:
            self.lbl_status.pack(fill=tk.X, pady=(4, 0))

    # ── Menú contextual ───────────────────────────────────────────────────────
    def _toggle_topmost(self):
        self._topmost = not self._topmost
        self.root.wm_attributes("-topmost", self._topmost)
        label = "  Siempre encima: ON" if self._topmost else "  Siempre encima: OFF"
        self.menu.entryconfig(2, label=label)

    def _show_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    # ── Animación del punto indicador ─────────────────────────────────────────
    def _blink_dot(self, color: str, times: int = 4, interval: int = 250):
        def toggle(n, on):
            self.dot.config(fg=color if on else DIM_COLOR)
            if n > 0:
                self.root.after(interval, toggle, n - 1, not on)
            else:
                self.dot.config(fg=color)
        toggle(times * 2, True)

    # ── Fetch precio ──────────────────────────────────────────────────────────
    def _fetch_price_once(self):
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            self.root.after(0, lambda: self.dot.config(fg="#AA4400"))
            req = urllib.request.Request(API_URL,
                  headers={"User-Agent": "BTCWidget/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
            price  = data["bitcoin"]["usd"]
            change = data["bitcoin"]["usd_24h_change"]
            self.root.after(0, self._update_ui, price, change, None)
        except Exception as e:
            self.root.after(0, self._update_ui, None, None, str(e)[:40])

    def _update_ui(self, price, change, error):
        if error:
            self.lbl_status.config(text=f"ERR: {error}", fg="#FF3333")
            self._blink_dot("#FF3333")
            return

        self.lbl_price.config(text=f" {price:,.2f}")

        arrow = "▲" if change >= 0 else "▼"
        color = CHANGE_POS if change >= 0 else CHANGE_NEG
        self.lbl_change.config(text=f"{arrow} {change:+.2f}%", fg=color)

        ts = time.strftime("%H:%M:%S")
        self.lbl_status.config(text=f"UPD {ts}  ·  cada {REFRESH_SEC}s",
                               fg="#C9A0DC")
        self._blink_dot(PRICE_COLOR)

    # ── Loop de actualización ─────────────────────────────────────────────────
    def _start_fetch_loop(self):
        self._fetch_price_once()
        self.root.after(REFRESH_SEC * 1000, self._schedule_next)

    def _schedule_next(self):
        self._fetch_price_once()
        self.root.after(REFRESH_SEC * 1000, self._schedule_next)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = BTCWidget(root)
    root.mainloop()
