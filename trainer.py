"""
EXAM TRAINER
Motor de practica de examenes de opcion multiple, dirigido por archivos JSON.

Interfaz de escritorio en tkinter: modos de practica, simulacro y examen
cronometrado, seguimiento de errores, estadisticas y progreso persistente.

El set de preguntas incluido es material original propio sobre AWS Cloud
Practitioner, escrito como demostracion. Para usar otro examen basta con
dejar tus propios archivos JSON en /data.

Sin dependencias externas: solo tkinter (libreria estandar).
"""

import json
import os
import random
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

APP_NAME = "Exam Trainer"
APP_SUBTITLE = "AWS Cloud Practitioner  ·  simulador de examen"
VERSION = "1.0"

# ----------------------------------------------------------------- paleta
C = {
    "bg":          "#f4f6fa",
    "card":        "#ffffff",
    "ink":         "#1d2733",
    "ink_soft":    "#5a6a80",
    "line":        "#dde4ee",

    "navy":        "#16233a",
    "navy_mid":    "#284a76",
    "blue":        "#2f6ba8",
    "blue_soft":   "#eaf2fb",

    "green":       "#2e9e5b",
    "green_soft":  "#e8f6ec",
    "red":         "#d64545",
    "red_soft":    "#fdecec",
    "amber":       "#c8892a",
    "amber_soft":  "#fdf3e2",
    "purple":      "#6b4bab",
    "purple_soft": "#f0ecfa",
    "gold":        "#b8912b",
    "gold_soft":   "#fbf5e3",
}

DOMAINS = [
    ("Cloud Concepts",              0.24),
    ("Security and Compliance",     0.30),
    ("Cloud Technology and Services", 0.34),
    ("Billing, Pricing and Support", 0.12),
]
DOMAIN_SHORT = {
    "Cloud Concepts": "Conceptos",
    "Security and Compliance": "Seguridad",
    "Cloud Technology and Services": "Tecnologia",
    "Billing, Pricing and Support": "Facturacion",
}

GAMEDAY_QUESTIONS = 65
GAMEDAY_MINUTES = 90
PASS_SCORE = 700

MODES = {
    "practica": ("PRACTICA", "Te digo al instante si fallaste, por que, y como identificarla."),
    "simulacro": ("SIMULACRO", "Contestas todo de corrido y reviso al final. Sin cronometro."),
    "gameday": ("GAME DAY", f"El examen de verdad: {GAMEDAY_QUESTIONS} preguntas, {GAMEDAY_MINUTES} minutos, pesos oficiales por dominio."),
    "errores": ("MIS ERRORES", "Solo las preguntas que ya has fallado antes."),
}


# ------------------------------------------------------------- utilidades

def resource_dir():
    """Carpeta de datos, funcione como script o como .exe de PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def progress_path():
    base = Path(os.environ.get("APPDATA") or Path.home())
    d = base / "ExamTrainer"
    d.mkdir(parents=True, exist_ok=True)
    return d / "progress.json"


def load_bank():
    """Banco base + sets adicionales + capa de tips, todo desde /data."""
    data_dir = resource_dir() / "data"
    data = []

    def read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"No se pudo leer {path.name}: {e}")
            return None

    base = data_dir / "bank.json"
    if base.exists():
        data.extend(read(base) or [])

    vdir = data_dir / "variants"
    if vdir.is_dir():
        for f in sorted(vdir.glob("*.json")):
            data.extend(read(f) or [])

    tips = {}
    tdir = data_dir / "tips"
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.json")):
            tips.update(read(f) or {})
    for q in data:
        if not q.get("tip") and q["id"] in tips:
            q["tip"] = tips[q["id"]]

    return data


def load_progress():
    p = progress_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"attempts": [], "questions": {}}


def save_progress(prog):
    try:
        progress_path().write_text(
            json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"No se pudo guardar el progreso: {e}")


def scaled_score(correct, total):
    """Aproximacion lineal a una escala 100-1000. 700 = aprobado."""
    if total == 0:
        return 100
    return int(round(100 + (correct / total) * 900))


def fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def gradient(canvas, w, h, c1, c2, tag="grad"):
    canvas.delete(tag)
    r1, g1, b1 = [v // 256 for v in canvas.winfo_rgb(c1)]
    r2, g2, b2 = [v // 256 for v in canvas.winfo_rgb(c2)]
    steps = max(1, w)
    for i in range(steps):
        t = i / steps
        col = f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"
        canvas.create_line(i, 0, i, h, fill=col, tags=tag)
    canvas.tag_lower(tag)


# --------------------------------------------------------------- widgets

class Scrollable(tk.Frame):
    """Contenedor con scroll vertical y rueda del mouse."""

    def __init__(self, parent, bg=C["bg"]):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.bind_all("<MouseWheel>", self._on_wheel)

    def _on_inner(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfig(self.win, width=e.width)

    def _on_wheel(self, e):
        try:
            if self.canvas.winfo_exists():
                self.canvas.yview_scroll(int(-e.delta / 120), "units")
        except tk.TclError:
            pass

    def to_top(self):
        self.canvas.yview_moveto(0)


def card(parent, accent=None, soft=None, pad=16):
    """Tarjeta blanca con borde, o con banda de color tipo callout de la guia."""
    outer = tk.Frame(parent, bg=accent or C["line"])
    inner = tk.Frame(outer, bg=soft or C["card"])
    inner.pack(fill="both", expand=True, padx=(4 if accent else 1, 1), pady=1)
    inner.configure(padx=pad, pady=pad)
    return outer, inner


def chip(parent, text, fg, bg):
    return tk.Label(parent, text=f"  {text}  ", bg=bg, fg=fg,
                    font=("Segoe UI", 9, "bold"), pady=3)


class Button(tk.Frame):
    """Boton plano con hover, porque los de tk se ven de 1998."""

    def __init__(self, parent, text, command, kind="primary", width=None):
        styles = {
            "primary": (C["blue"], "#ffffff", "#255a90"),
            "dark":    (C["navy"], "#ffffff", "#0f1929"),
            "green":   (C["green"], "#ffffff", "#248049"),
            "red":     (C["red"], "#ffffff", "#b23838"),
            "ghost":   ("#ffffff", C["ink"], "#eef2f8"),
        }
        bg, fg, hover = styles[kind]
        super().__init__(parent, bg=bg, highlightthickness=1,
                         highlightbackground=C["line"] if kind == "ghost" else bg)
        self.bg, self.hover, self.command = bg, hover, command
        self.lbl = tk.Label(self, text=text, bg=bg, fg=fg,
                            font=("Segoe UI", 10, "bold"), padx=18, pady=9,
                            cursor="hand2")
        if width:
            self.lbl.configure(width=width)
        self.lbl.pack(fill="both", expand=True)
        for w in (self, self.lbl):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _click(self, _=None):
        if self.command:
            self.command()

    def _enter(self, _=None):
        self.configure(bg=self.hover)
        self.lbl.configure(bg=self.hover)

    def _leave(self, _=None):
        self.configure(bg=self.bg)
        self.lbl.configure(bg=self.bg)


class OptionRow(tk.Frame):
    """Una opcion clickeable, estilo tarjeta."""

    def __init__(self, parent, letter, text, on_click, wrap=760):
        super().__init__(parent, bg=C["card"], highlightthickness=2,
                         highlightbackground=C["line"], cursor="hand2")
        self.letter, self.on_click = letter, on_click
        self.state = "idle"

        self.badge = tk.Label(self, text=letter, width=3, bg=C["blue_soft"],
                              fg=C["blue"], font=("Segoe UI", 11, "bold"), pady=6)
        self.badge.pack(side="left", fill="y", padx=(10, 12), pady=10)

        self.lbl = tk.Label(self, text=text, bg=C["card"], fg=C["ink"],
                            font=("Segoe UI", 10), justify="left",
                            anchor="w", wraplength=wrap)
        self.lbl.pack(side="left", fill="both", expand=True, pady=10, padx=(0, 12))

        for w in (self, self.badge, self.lbl):
            w.bind("<Button-1>", lambda _e: self.on_click(self.letter))

    def paint(self, state):
        self.state = state
        looks = {
            "idle":     (C["card"], C["line"], C["blue_soft"], C["blue"]),
            "selected": (C["blue_soft"], C["blue"], C["blue"], "#ffffff"),
            "correct":  (C["green_soft"], C["green"], C["green"], "#ffffff"),
            "wrong":    (C["red_soft"], C["red"], C["red"], "#ffffff"),
            "missed":   (C["green_soft"], C["green"], C["green_soft"], C["green"]),
        }
        bg, border, bbg, bfg = looks[state]
        self.configure(bg=bg, highlightbackground=border)
        self.lbl.configure(bg=bg)
        self.badge.configure(bg=bbg, fg=bfg)

    def set_wrap(self, px):
        self.lbl.configure(wraplength=max(240, px))


# ------------------------------------------------------------------- app

class Trainer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{VERSION}")
        self.geometry("1120x800")
        self.minsize(940, 660)
        self.configure(bg=C["bg"])

        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Segoe UI", size=10)
        except tk.TclError:
            pass

        self.bank = load_bank()
        if not self.bank:
            messagebox.showerror(APP_NAME, "No encontre el banco de preguntas.\n"
                                           "Falta la carpeta 'data' junto al ejecutable.")
            self.destroy()
            return
        self.progress = load_progress()

        self.header = tk.Canvas(self, height=76, highlightthickness=0, bd=0)
        self.header.pack(fill="x")
        self.header.bind("<Configure>", self._paint_header)

        self.body = tk.Frame(self, bg=C["bg"])
        self.body.pack(fill="both", expand=True)

        self.session = None
        self.show_home()

    # ------------------------------------------------------------ chrome
    def _paint_header(self, _=None):
        w = self.header.winfo_width()
        h = self.header.winfo_height()
        gradient(self.header, w, h, C["navy"], C["blue"])
        self.header.delete("txt")
        self.header.create_text(28, 26, anchor="w", text=APP_NAME.upper(),
                                fill="#ffffff", font=("Segoe UI", 17, "bold"),
                                tags="txt")
        self.header.create_text(30, 52, anchor="w",
                                text=APP_SUBTITLE,
                                fill="#bcd4ec", font=("Segoe UI", 9), tags="txt")
        if self.session and self.session.get("mode") == "gameday":
            self.header.create_text(w - 28, 38, anchor="e", text=self._clock_text,
                                    fill="#ffffff", font=("Consolas", 20, "bold"),
                                    tags="txt")

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    # -------------------------------------------------------------- home
    def show_home(self):
        self.session = None
        self.clear()
        self._paint_header()

        sc = Scrollable(self.body)
        sc.pack(fill="both", expand=True)
        page = tk.Frame(sc.inner, bg=C["bg"])
        page.pack(fill="both", expand=True, padx=34, pady=26)

        tk.Label(page, text="Arma tu examen", bg=C["bg"], fg=C["ink"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(page, text=f"{len(self.bank)} preguntas en el banco  ·  "
                            f"{len(set(q['chapter'] for q in self.bank))} capitulos",
                 bg=C["bg"], fg=C["ink_soft"], font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 18))

        # --- modo
        self.mode_var = tk.StringVar(value="practica")
        tk.Label(page, text="1.  MODO", bg=C["bg"], fg=C["blue"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        grid = tk.Frame(page, bg=C["bg"])
        grid.pack(fill="x", pady=(0, 22))
        for i in range(2):
            grid.columnconfigure(i, weight=1, uniform="m")

        self.mode_cards = {}
        for i, (key, (name, desc)) in enumerate(MODES.items()):
            accent = C["gold"] if key == "gameday" else C["blue"]
            f = tk.Frame(grid, bg=C["card"], highlightthickness=2,
                         highlightbackground=C["line"], cursor="hand2")
            f.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            t = tk.Label(f, text=name, bg=C["card"], fg=accent,
                         font=("Segoe UI", 12, "bold"), anchor="w")
            t.pack(fill="x", padx=16, pady=(14, 2))
            d = tk.Label(f, text=desc, bg=C["card"], fg=C["ink_soft"],
                         font=("Segoe UI", 9), anchor="w", justify="left",
                         wraplength=430)
            d.pack(fill="x", padx=16, pady=(0, 14))
            self.mode_cards[key] = (f, t, d, accent)
            for w in (f, t, d):
                w.bind("<Button-1>", lambda _e, k=key: self._pick_mode(k))
        self._pick_mode("practica")

        # --- alcance
        tk.Label(page, text="2.  CAPITULOS", bg=C["bg"], fg=C["blue"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        self.chap_vars = {}
        chaps = sorted(set(q["chapter"] for q in self.bank))
        titles = {q["chapter"]: q["chapter_title"] for q in self.bank}

        cbox = tk.Frame(page, bg=C["card"], highlightthickness=1,
                        highlightbackground=C["line"])
        cbox.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(cbox, bg=C["card"])
        inner.pack(fill="x", padx=14, pady=12)
        for i in range(3):
            inner.columnconfigure(i, weight=1, uniform="c")

        for i, ch in enumerate(chaps):
            v = tk.BooleanVar(value=True)
            self.chap_vars[ch] = v
            n = sum(1 for q in self.bank if q["chapter"] == ch)
            tk.Checkbutton(inner, text=f"{ch:>2}. {titles[ch][:34]}  ({n})",
                           variable=v, bg=C["card"], fg=C["ink"], anchor="w",
                           font=("Segoe UI", 9), activebackground=C["card"],
                           selectcolor=C["card"], highlightthickness=0,
                           command=self._refresh_count
                           ).grid(row=i // 3, column=i % 3, sticky="w", pady=2)

        row = tk.Frame(page, bg=C["bg"])
        row.pack(fill="x", pady=(0, 22))
        Button(row, "Todos", lambda: self._set_all(True), kind="ghost").pack(side="left")
        Button(row, "Ninguno", lambda: self._set_all(False), kind="ghost").pack(side="left", padx=8)

        # --- cantidad
        tk.Label(page, text="3.  CUANTAS PREGUNTAS", bg=C["bg"], fg=C["blue"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        qrow = tk.Frame(page, bg=C["bg"])
        qrow.pack(fill="x", pady=(0, 6))
        self.count_var = tk.IntVar(value=20)
        self.count_btns = {}
        for n in (10, 20, 30, 50, 65, 0):
            label = "TODAS" if n == 0 else str(n)
            b = tk.Label(qrow, text=label, width=7, bg=C["card"], fg=C["ink"],
                         font=("Segoe UI", 10, "bold"), pady=9, cursor="hand2",
                         highlightthickness=2, highlightbackground=C["line"])
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda _e, v=n: self._pick_count(v))
            self.count_btns[n] = b
        self._pick_count(20)

        self.count_note = tk.Label(page, text="", bg=C["bg"], fg=C["ink_soft"],
                                   font=("Segoe UI", 9))
        self.count_note.pack(anchor="w", pady=(6, 20))
        self._refresh_count()

        # --- lanzar
        go = tk.Frame(page, bg=C["bg"])
        go.pack(fill="x", pady=(4, 26))
        Button(go, "COMENZAR EXAMEN", self.start_session, kind="dark").pack(side="left")
        Button(go, "Ver mis estadisticas", self.show_stats, kind="ghost").pack(side="left", padx=10)

        self._home_stats(page)

    def _pick_mode(self, key):
        self.mode_var.set(key)
        for k, (f, t, d, accent) in self.mode_cards.items():
            on = (k == key)
            f.configure(highlightbackground=accent if on else C["line"],
                        bg=C["blue_soft"] if on and k != "gameday" else
                           (C["gold_soft"] if on else C["card"]))
            bg = f.cget("bg")
            t.configure(bg=bg)
            d.configure(bg=bg)
        if hasattr(self, "count_note"):
            self._refresh_count()

    def _pick_count(self, n):
        self.count_var.set(n)
        for k, b in self.count_btns.items():
            on = (k == n)
            b.configure(bg=C["blue"] if on else C["card"],
                        fg="#ffffff" if on else C["ink"],
                        highlightbackground=C["blue"] if on else C["line"])
        if hasattr(self, "count_note"):
            self._refresh_count()

    def _set_all(self, val):
        for v in self.chap_vars.values():
            v.set(val)
        self._refresh_count()

    def _pool(self):
        mode = self.mode_var.get()
        chaps = {c for c, v in self.chap_vars.items() if v.get()}
        pool = [q for q in self.bank if q["chapter"] in chaps]
        if mode == "errores":
            stats = self.progress["questions"]
            pool = [q for q in pool if stats.get(q["id"], {}).get("wrong", 0) > 0]
        return pool

    def _refresh_count(self):
        mode = self.mode_var.get()
        pool = self._pool()
        if mode == "gameday":
            self.count_note.configure(
                text=f"GAME DAY ignora estos ajustes: siempre son {GAMEDAY_QUESTIONS} "
                     f"preguntas en {GAMEDAY_MINUTES} minutos, repartidas por los pesos "
                     f"oficiales de cada dominio.")
        elif mode == "errores":
            self.count_note.configure(
                text=f"Tenes {len(pool)} preguntas falladas disponibles."
                if pool else "Todavia no has fallado ninguna pregunta. Hace un examen primero.")
        else:
            want = self.count_var.get() or len(pool)
            self.count_note.configure(
                text=f"Disponibles: {len(pool)}  ·  se usaran {min(want, len(pool))}")

    def _home_stats(self, page):
        att = self.progress["attempts"]
        if not att:
            return
        box, inner = card(page, accent=C["blue"], soft=C["blue_soft"])
        box.pack(fill="x")
        tk.Label(inner, text="TU ULTIMO INTENTO", bg=C["blue_soft"], fg=C["blue"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        a = att[-1]
        tk.Label(inner, text=f"{a['mode'].upper()}  ·  {a['correct']}/{a['total']} correctas  "
                             f"·  {a['score']} puntos  ·  {a['date'][:16]}",
                 bg=C["blue_soft"], fg=C["ink"], font=("Segoe UI", 11, "bold")
                 ).pack(anchor="w", pady=(4, 0))

    # ----------------------------------------------------------- armado
    def build_questions(self):
        mode = self.mode_var.get()
        pool = self._pool()
        if not pool:
            messagebox.showwarning(APP_NAME, "No hay preguntas con esos filtros.")
            return None

        if mode == "gameday":
            picked, by_dom = [], {}
            for q in self.bank:
                by_dom.setdefault(q["domain"], []).append(q)
            for dom, weight in DOMAINS:
                want = round(GAMEDAY_QUESTIONS * weight)
                avail = by_dom.get(dom, [])
                picked.extend(random.sample(avail, min(want, len(avail))))
            rest = [q for q in self.bank if q not in picked]
            random.shuffle(rest)
            picked.extend(rest[:max(0, GAMEDAY_QUESTIONS - len(picked))])
            picked = picked[:GAMEDAY_QUESTIONS]
        else:
            want = self.count_var.get() or len(pool)
            picked = random.sample(pool, min(want, len(pool)))

        random.shuffle(picked)

        # se barajan tambien las opciones para que no memorices "la C"
        items = []
        for q in picked:
            letters = sorted(q["options"].keys())
            texts = [q["options"][l] for l in letters]
            order = list(range(len(letters)))
            random.shuffle(order)
            new_opts, remap = {}, {}
            for new_i, old_i in enumerate(order):
                new_letter = chr(ord("A") + new_i)
                new_opts[new_letter] = texts[old_i]
                remap[letters[old_i]] = new_letter
            items.append({
                "q": q,
                "options": new_opts,
                "answer": sorted(remap[a] for a in q["answer"] if a in remap),
                "picked": set(),
                "flagged": False,
                "checked": False,
            })
        return items

    def start_session(self):
        items = self.build_questions()
        if not items:
            return
        mode = self.mode_var.get()
        self.session = {
            "mode": mode,
            "items": items,
            "idx": 0,
            "start": time.time(),
            "deadline": time.time() + GAMEDAY_MINUTES * 60 if mode == "gameday" else None,
        }
        self._clock_text = fmt_time(GAMEDAY_MINUTES * 60)
        if mode == "gameday":
            self._tick()
        self.show_question()

    def _tick(self):
        s = self.session
        if not s or s.get("mode") != "gameday" or not s.get("deadline"):
            return
        left = s["deadline"] - time.time()
        self._clock_text = fmt_time(left)
        self._paint_header()
        if left <= 0:
            messagebox.showinfo(APP_NAME, "Se acabo el tiempo. Se califica lo que llevas.")
            self.finish()
            return
        self.after(1000, self._tick)

    # --------------------------------------------------------- pregunta
    def show_question(self):
        self.clear()
        s = self.session
        item = s["items"][s["idx"]]
        q = item["q"]
        practice = s["mode"] == "practica"

        # barra superior
        bar = tk.Frame(self.body, bg=C["card"], height=54)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=f"Pregunta {s['idx']+1} de {len(s['items'])}",
                 bg=C["card"], fg=C["ink"], font=("Segoe UI", 11, "bold")
                 ).pack(side="left", padx=22)

        chip(bar, DOMAIN_SHORT.get(q["domain"], q["domain"]),
             C["purple"], C["purple_soft"]).pack(side="left", padx=4)
        if s["mode"] != "gameday":
            chip(bar, f"Cap {q['chapter']}", C["blue"], C["blue_soft"]).pack(side="left", padx=4)
        if item["answer"] and len(item["answer"]) > 1:
            chip(bar, f"ELIGE {len(item['answer'])}", C["amber"], C["amber_soft"]).pack(side="left", padx=4)

        self.flag_lbl = tk.Label(bar, text="", bg=C["card"], fg=C["amber"],
                                 font=("Segoe UI", 9, "bold"), cursor="hand2")
        self.flag_lbl.pack(side="right", padx=22)
        self.flag_lbl.bind("<Button-1>", lambda _e: self._toggle_flag())
        self._paint_flag()

        # barra de progreso
        pb = tk.Canvas(self.body, height=4, highlightthickness=0, bg=C["line"])
        pb.pack(fill="x")
        pb.bind("<Configure>", lambda e, c=pb: (
            c.delete("p"),
            c.create_rectangle(0, 0, e.width * (s["idx"] + 1) / len(s["items"]), 4,
                               fill=C["blue"], width=0, tags="p")))

        # cuerpo
        sc = Scrollable(self.body)
        sc.pack(fill="both", expand=True)
        self.qpage = tk.Frame(sc.inner, bg=C["bg"])
        self.qpage.pack(fill="both", expand=True, padx=34, pady=24)

        self.qtext = tk.Label(self.qpage, text=q["text"], bg=C["bg"], fg=C["ink"],
                              font=("Segoe UI", 13), justify="left", anchor="w",
                              wraplength=820)
        self.qtext.pack(fill="x", pady=(0, 20))

        self.rows = {}
        for letter, text in sorted(item["options"].items()):
            r = OptionRow(self.qpage, letter, text, self._choose)
            r.pack(fill="x", pady=4)
            self.rows[letter] = r

        self.fb_holder = tk.Frame(self.qpage, bg=C["bg"])
        self.fb_holder.pack(fill="x", pady=(18, 0))

        self.body.bind("<Configure>", self._rewrap)

        # pie
        foot = tk.Frame(self.body, bg=C["card"], height=64)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        pad = tk.Frame(foot, bg=C["card"])
        pad.pack(fill="both", expand=True, padx=22, pady=12)

        if s["idx"] > 0:
            Button(pad, "< Anterior", self.prev_q, kind="ghost").pack(side="left")

        Button(pad, "Terminar y calificar", self.confirm_finish, kind="ghost").pack(side="right")
        self.next_btn = Button(pad, "Siguiente >", self.next_q, kind="primary")
        self.next_btn.pack(side="right", padx=10)

        if practice:
            self.check_btn = Button(pad, "Comprobar", self.check_now, kind="green")
            self.check_btn.pack(side="right", padx=4)

        self.repaint_options()
        if item["checked"]:
            self.render_feedback()
        sc.to_top()

    def _rewrap(self, _=None):
        w = max(400, self.body.winfo_width() - 120)
        try:
            self.qtext.configure(wraplength=w)
            for r in self.rows.values():
                r.set_wrap(w - 90)
        except (tk.TclError, AttributeError):
            pass

    def _paint_flag(self):
        item = self.session["items"][self.session["idx"]]
        self.flag_lbl.configure(
            text="[X]  Marcada para revisar" if item["flagged"] else "[ ]  Marcar para revisar")

    def _toggle_flag(self):
        item = self.session["items"][self.session["idx"]]
        item["flagged"] = not item["flagged"]
        self._paint_flag()

    def _choose(self, letter):
        s = self.session
        item = s["items"][s["idx"]]
        if item["checked"]:
            return
        multi = len(item["answer"]) > 1
        if multi:
            item["picked"] ^= {letter}
        else:
            item["picked"] = {letter}
        self.repaint_options()

    def repaint_options(self):
        item = self.session["items"][self.session["idx"]]
        for letter, row in self.rows.items():
            if not item["checked"]:
                row.paint("selected" if letter in item["picked"] else "idle")
            else:
                if letter in item["answer"] and letter in item["picked"]:
                    row.paint("correct")
                elif letter in item["answer"]:
                    row.paint("missed")
                elif letter in item["picked"]:
                    row.paint("wrong")
                else:
                    row.paint("idle")

    def check_now(self):
        item = self.session["items"][self.session["idx"]]
        if not item["picked"]:
            messagebox.showinfo(APP_NAME, "Elegi una respuesta primero.")
            return
        need = len(item["answer"])
        if len(item["picked"]) != need:
            messagebox.showinfo(APP_NAME, f"Esta pregunta pide {need} respuestas. "
                                          f"Llevas {len(item['picked'])}.")
            return
        item["checked"] = True
        self.repaint_options()
        self.render_feedback()

    def render_feedback(self):
        for w in self.fb_holder.winfo_children():
            w.destroy()
        item = self.session["items"][self.session["idx"]]
        q = item["q"]
        ok = item["picked"] == set(item["answer"])

        accent = C["green"] if ok else C["red"]
        soft = C["green_soft"] if ok else C["red_soft"]
        box, inner = card(self.fb_holder, accent=accent, soft=soft)
        box.pack(fill="x")

        tk.Label(inner, text="CORRECTO" if ok else "INCORRECTO", bg=soft, fg=accent,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        tk.Label(inner, text=f"Respuesta correcta:  {', '.join(item['answer'])}",
                 bg=soft, fg=C["ink"], font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", pady=(6, 10))

        tk.Label(inner, text=q["explanation_en"], bg=soft, fg=C["ink"],
                 font=("Segoe UI", 10), justify="left", anchor="w",
                 wraplength=self.body.winfo_width() - 160).pack(fill="x")

        if q.get("explanation_es"):
            tk.Label(inner, text=q["explanation_es"], bg=soft, fg=C["ink"],
                     font=("Segoe UI", 10), justify="left", anchor="w",
                     wraplength=self.body.winfo_width() - 160).pack(fill="x", pady=(10, 0))

        if q.get("tip"):
            tbox, tin = card(self.fb_holder, accent=C["gold"], soft=C["gold_soft"], pad=14)
            tbox.pack(fill="x", pady=(10, 0))
            tk.Label(tin, text="COMO IDENTIFICARLA", bg=C["gold_soft"], fg=C["gold"],
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(tin, text=q["tip"], bg=C["gold_soft"], fg=C["ink"],
                     font=("Segoe UI", 10), justify="left", anchor="w",
                     wraplength=self.body.winfo_width() - 160).pack(fill="x", pady=(4, 0))

        tk.Label(self.fb_holder,
                 text=f"Repasa el Capitulo {q['chapter']} - {q['chapter_title']}",
                 bg=C["bg"], fg=C["ink_soft"], font=("Segoe UI", 9, "italic")
                 ).pack(anchor="w", pady=(8, 0))

    def next_q(self):
        s = self.session
        if s["idx"] < len(s["items"]) - 1:
            s["idx"] += 1
            self.show_question()
        else:
            self.show_review()

    def prev_q(self):
        s = self.session
        if s["idx"] > 0:
            s["idx"] -= 1
            self.show_question()

    def confirm_finish(self):
        if messagebox.askyesno(APP_NAME, "Terminar y calificar ahora?"):
            self.finish()

    # ---------------------------------------------------------- revision
    def show_review(self):
        self.clear()
        s = self.session
        sc = Scrollable(self.body)
        sc.pack(fill="both", expand=True)
        page = tk.Frame(sc.inner, bg=C["bg"])
        page.pack(fill="both", expand=True, padx=34, pady=26)

        tk.Label(page, text="Antes de calificar", bg=C["bg"], fg=C["ink"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w")
        blank = sum(1 for it in s["items"] if not it["picked"])
        flagged = sum(1 for it in s["items"] if it["flagged"])
        tk.Label(page, text=f"{blank} sin contestar  ·  {flagged} marcadas para revisar",
                 bg=C["bg"], fg=C["ink_soft"], font=("Segoe UI", 10)
                 ).pack(anchor="w", pady=(2, 18))

        grid = tk.Frame(page, bg=C["bg"])
        grid.pack(fill="x", pady=(0, 24))
        cols = 13
        for i, it in enumerate(s["items"]):
            if it["flagged"]:
                bg, fg = C["amber_soft"], C["amber"]
            elif it["picked"]:
                bg, fg = C["blue"], "#ffffff"
            else:
                bg, fg = C["card"], C["ink_soft"]
            b = tk.Label(grid, text=str(i + 1), width=4, pady=7, bg=bg, fg=fg,
                         font=("Segoe UI", 9, "bold"), cursor="hand2",
                         highlightthickness=1, highlightbackground=C["line"])
            b.grid(row=i // cols, column=i % cols, padx=3, pady=3)
            b.bind("<Button-1>", lambda _e, n=i: self._jump(n))

        row = tk.Frame(page, bg=C["bg"])
        row.pack(fill="x")
        Button(row, "CALIFICAR", self.finish, kind="dark").pack(side="left")
        Button(row, "Volver a las preguntas", lambda: self._jump(0),
               kind="ghost").pack(side="left", padx=10)

    def _jump(self, n):
        self.session["idx"] = n
        self.show_question()

    # --------------------------------------------------------- resultados
    def finish(self):
        s = self.session
        s["deadline"] = None
        items = s["items"]
        correct = sum(1 for it in items if it["picked"] == set(it["answer"]))
        total = len(items)
        score = scaled_score(correct, total)
        elapsed = time.time() - s["start"]

        qstats = self.progress["questions"]
        for it in items:
            e = qstats.setdefault(it["q"]["id"], {"seen": 0, "wrong": 0})
            e["seen"] += 1
            if it["picked"] != set(it["answer"]):
                e["wrong"] += 1
            elif e["wrong"] > 0 and s["mode"] != "practica":
                e["wrong"] = max(0, e["wrong"] - 1)

        self.progress["attempts"].append({
            "date": datetime.now().isoformat(timespec="seconds"),
            "mode": s["mode"], "total": total, "correct": correct,
            "score": score, "seconds": int(elapsed),
        })
        save_progress(self.progress)
        self.show_results(correct, total, score, elapsed)

    def show_results(self, correct, total, score, elapsed):
        self.clear()
        self._paint_header()
        s = self.session
        passed = score >= PASS_SCORE

        sc = Scrollable(self.body)
        sc.pack(fill="both", expand=True)
        page = tk.Frame(sc.inner, bg=C["bg"])
        page.pack(fill="both", expand=True, padx=34, pady=26)

        # marcador
        accent = C["green"] if passed else C["red"]
        soft = C["green_soft"] if passed else C["red_soft"]
        box, inner = card(page, accent=accent, soft=soft, pad=22)
        box.pack(fill="x")

        tk.Label(inner, text="APROBADO" if passed else "NO APROBADO",
                 bg=soft, fg=accent, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(inner, text=f"{score} / 1000     (se aprueba con {PASS_SCORE})",
                 bg=soft, fg=C["ink"], font=("Segoe UI", 13, "bold")
                 ).pack(anchor="w", pady=(4, 0))
        tk.Label(inner, text=f"{correct} de {total} correctas  ·  "
                             f"{correct/total*100:.0f}%  ·  tiempo {fmt_time(elapsed)}",
                 bg=soft, fg=C["ink_soft"], font=("Segoe UI", 10)
                 ).pack(anchor="w", pady=(6, 0))
        tk.Label(inner, text="El puntaje es una aproximacion lineal a una escala de 100 a 1000.",
                 bg=soft, fg=C["ink_soft"], font=("Segoe UI", 8, "italic")
                 ).pack(anchor="w", pady=(6, 0))

        # desglose
        self._breakdown(page, "POR DOMINIO", lambda it: it["q"]["domain"])
        self._breakdown(page, "POR CAPITULO",
                        lambda it: f"Cap {it['q']['chapter']:>2} - {it['q']['chapter_title']}")

        # fallos
        wrong = [it for it in s["items"] if it["picked"] != set(it["answer"])]
        if wrong:
            tk.Label(page, text=f"LO QUE FALLASTE  ({len(wrong)})", bg=C["bg"],
                     fg=C["red"], font=("Segoe UI", 11, "bold")
                     ).pack(anchor="w", pady=(24, 10))
            for it in wrong:
                self._wrong_card(page, it)

        row = tk.Frame(page, bg=C["bg"])
        row.pack(fill="x", pady=26)
        Button(row, "Otro examen igual", self.start_session, kind="dark").pack(side="left")
        Button(row, "Inicio", self.show_home, kind="ghost").pack(side="left", padx=10)
        Button(row, "Estadisticas", self.show_stats, kind="ghost").pack(side="left")

    def _breakdown(self, page, title, keyfn):
        s = self.session
        buckets = {}
        for it in s["items"]:
            k = keyfn(it)
            b = buckets.setdefault(k, [0, 0])
            b[1] += 1
            if it["picked"] == set(it["answer"]):
                b[0] += 1
        if len(buckets) < 2:
            return

        tk.Label(page, text=title, bg=C["bg"], fg=C["blue"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(24, 10))
        box = tk.Frame(page, bg=C["card"], highlightthickness=1,
                       highlightbackground=C["line"])
        box.pack(fill="x")
        inner = tk.Frame(box, bg=C["card"])
        inner.pack(fill="x", padx=18, pady=14)

        for k in sorted(buckets):
            got, tot = buckets[k]
            pct = got / tot
            r = tk.Frame(inner, bg=C["card"])
            r.pack(fill="x", pady=3)
            tk.Label(r, text=DOMAIN_SHORT.get(k, k)[:42], width=40, anchor="w",
                     bg=C["card"], fg=C["ink"], font=("Segoe UI", 9)).pack(side="left")
            cv = tk.Canvas(r, height=16, bg=C["bg"], highlightthickness=0)
            cv.pack(side="left", fill="x", expand=True, padx=10)
            col = C["green"] if pct >= 0.8 else (C["amber"] if pct >= 0.6 else C["red"])
            cv.bind("<Configure>", lambda e, c=cv, p=pct, col=col: (
                c.delete("b"),
                c.create_rectangle(0, 0, max(2, e.width * p), 16, fill=col,
                                   width=0, tags="b")))
            tk.Label(r, text=f"{got}/{tot}", width=7, anchor="e", bg=C["card"],
                     fg=C["ink_soft"], font=("Segoe UI", 9, "bold")).pack(side="left")

    def _wrong_card(self, page, it):
        q = it["q"]
        box, inner = card(page, accent=C["red"], soft=C["card"], pad=16)
        box.pack(fill="x", pady=5)

        tk.Label(inner, text=q["text"], bg=C["card"], fg=C["ink"],
                 font=("Segoe UI", 10, "bold"), justify="left", anchor="w",
                 wraplength=self.body.winfo_width() - 140).pack(fill="x")

        for letter, text in sorted(it["options"].items()):
            mark, col = "   ", C["ink_soft"]
            if letter in it["answer"]:
                mark, col = " > ", C["green"]
            elif letter in it["picked"]:
                mark, col = " X ", C["red"]
            tk.Label(inner, text=f"{mark}{letter}. {text}", bg=C["card"], fg=col,
                     font=("Segoe UI", 9, "bold" if mark != "   " else "normal"),
                     justify="left", anchor="w",
                     wraplength=self.body.winfo_width() - 150).pack(fill="x", pady=1)

        tk.Label(inner, text=q["explanation_en"], bg=C["card"], fg=C["ink_soft"],
                 font=("Segoe UI", 9), justify="left", anchor="w",
                 wraplength=self.body.winfo_width() - 140).pack(fill="x", pady=(8, 0))

        if q.get("tip"):
            tk.Label(inner, text=f"COMO IDENTIFICARLA:  {q['tip']}", bg=C["card"],
                     fg=C["gold"], font=("Segoe UI", 9, "bold"), justify="left",
                     anchor="w", wraplength=self.body.winfo_width() - 140
                     ).pack(fill="x", pady=(6, 0))

        tk.Label(inner, text=f"Capitulo {q['chapter']} - {q['chapter_title']}",
                 bg=C["card"], fg=C["blue"], font=("Segoe UI", 8, "italic")
                 ).pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------ estadisticas
    def show_stats(self):
        self.session = None
        self.clear()
        self._paint_header()

        sc = Scrollable(self.body)
        sc.pack(fill="both", expand=True)
        page = tk.Frame(sc.inner, bg=C["bg"])
        page.pack(fill="both", expand=True, padx=34, pady=26)

        tk.Label(page, text="Tu progreso", bg=C["bg"], fg=C["ink"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 18))

        att = self.progress["attempts"]
        if not att:
            tk.Label(page, text="Todavia no has hecho ningun examen.", bg=C["bg"],
                     fg=C["ink_soft"], font=("Segoe UI", 11)).pack(anchor="w")
            Button(page, "Inicio", self.show_home, kind="dark").pack(anchor="w", pady=20)
            return

        best = max(a["score"] for a in att)
        avg = sum(a["score"] for a in att) / len(att)
        passes = sum(1 for a in att if a["score"] >= PASS_SCORE)

        strip = tk.Frame(page, bg=C["bg"])
        strip.pack(fill="x", pady=(0, 24))
        for label, value, col in (("Examenes", len(att), C["blue"]),
                                  ("Mejor puntaje", best, C["green"] if best >= PASS_SCORE else C["amber"]),
                                  ("Promedio", int(avg), C["blue"]),
                                  ("Aprobados", f"{passes}/{len(att)}", C["purple"])):
            f = tk.Frame(strip, bg=C["card"], highlightthickness=1,
                         highlightbackground=C["line"])
            f.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(f, text=str(value), bg=C["card"], fg=col,
                     font=("Segoe UI", 20, "bold")).pack(pady=(14, 0))
            tk.Label(f, text=label, bg=C["card"], fg=C["ink_soft"],
                     font=("Segoe UI", 9)).pack(pady=(0, 14))

        # dominio de cada capitulo
        qstats = self.progress["questions"]
        by_ch = {}
        for q in self.bank:
            st = qstats.get(q["id"])
            if not st or not st.get("seen"):
                continue
            b = by_ch.setdefault(q["chapter"], [0, 0, q["chapter_title"]])
            b[0] += st["seen"] - st["wrong"]
            b[1] += st["seen"]

        if by_ch:
            tk.Label(page, text="DOMINIO POR CAPITULO", bg=C["bg"], fg=C["blue"],
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
            box = tk.Frame(page, bg=C["card"], highlightthickness=1,
                           highlightbackground=C["line"])
            box.pack(fill="x")
            inner = tk.Frame(box, bg=C["card"])
            inner.pack(fill="x", padx=18, pady=14)
            for ch in sorted(by_ch):
                got, tot, title = by_ch[ch]
                pct = max(0, got) / tot
                r = tk.Frame(inner, bg=C["card"])
                r.pack(fill="x", pady=3)
                tk.Label(r, text=f"{ch:>2}. {title[:38]}", width=42, anchor="w",
                         bg=C["card"], fg=C["ink"], font=("Segoe UI", 9)).pack(side="left")
                cv = tk.Canvas(r, height=16, bg=C["bg"], highlightthickness=0)
                cv.pack(side="left", fill="x", expand=True, padx=10)
                col = C["green"] if pct >= 0.8 else (C["amber"] if pct >= 0.6 else C["red"])
                cv.bind("<Configure>", lambda e, c=cv, p=pct, col=col: (
                    c.delete("b"),
                    c.create_rectangle(0, 0, max(2, e.width * p), 16, fill=col,
                                       width=0, tags="b")))
                tk.Label(r, text=f"{pct*100:.0f}%", width=6, anchor="e", bg=C["card"],
                         fg=C["ink_soft"], font=("Segoe UI", 9, "bold")).pack(side="left")

        # historial
        tk.Label(page, text="HISTORIAL", bg=C["bg"], fg=C["blue"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(24, 10))
        box = tk.Frame(page, bg=C["card"], highlightthickness=1,
                       highlightbackground=C["line"])
        box.pack(fill="x")
        inner = tk.Frame(box, bg=C["card"])
        inner.pack(fill="x", padx=18, pady=14)
        for a in reversed(att[-25:]):
            r = tk.Frame(inner, bg=C["card"])
            r.pack(fill="x", pady=2)
            ok = a["score"] >= PASS_SCORE
            tk.Label(r, text=a["date"][:16].replace("T", "  "), width=18, anchor="w",
                     bg=C["card"], fg=C["ink_soft"], font=("Segoe UI", 9)).pack(side="left")
            tk.Label(r, text=a["mode"].upper(), width=12, anchor="w", bg=C["card"],
                     fg=C["ink"], font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Label(r, text=f"{a['correct']}/{a['total']}", width=8, anchor="w",
                     bg=C["card"], fg=C["ink"], font=("Segoe UI", 9)).pack(side="left")
            tk.Label(r, text=f"{a['score']}", width=7, anchor="w", bg=C["card"],
                     fg=C["green"] if ok else C["red"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Label(r, text=fmt_time(a["seconds"]), anchor="w", bg=C["card"],
                     fg=C["ink_soft"], font=("Segoe UI", 9)).pack(side="left")

        row = tk.Frame(page, bg=C["bg"])
        row.pack(fill="x", pady=24)
        Button(row, "Inicio", self.show_home, kind="dark").pack(side="left")
        Button(row, "Borrar historial", self.reset_progress, kind="ghost").pack(side="left", padx=10)

    def reset_progress(self):
        if messagebox.askyesno(APP_NAME, "Borrar todo tu historial y estadisticas?"):
            self.progress = {"attempts": [], "questions": {}}
            save_progress(self.progress)
            self.show_stats()


def main():
    app = Trainer()
    if app.winfo_exists():
        app.mainloop()


if __name__ == "__main__":
    main()
