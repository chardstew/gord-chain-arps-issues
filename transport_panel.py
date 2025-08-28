# transport_panel.py

import tkinter as tk
from PIL import Image, ImageTk
from config import (
    COLORS, NOTE_TO_COLOR,
    DEFAULT_TEMPO, DEFAULT_GATE, DEFAULT_SUBDIVISION
)
from export_panel import ExportPanel
from utils import resource_path


class TransportPanel(tk.Frame):
    """
    Middle-column stack:
        • Root label
        • Start/Stop/Random/Clear buttons
        • BPM slider + entry
        • Gate slider + entry
        • Subdivision buttons 1/4-1/32
        • Direction buttons (⇒, ⇐, ⇄, ⇆) with include_turnaround toggling
        • Icon (double-click toggles slave mode)
        • Folder/Get Arp/Get Chord (ExportPanel)
    """
    def __init__(
        self, master, state,
        icon_path,
        on_start, on_stop, on_random, on_clear,
        on_direction_change=None
    ):
        super().__init__(master, bg=COLORS['bg'])
        self.state = state
        self.on_start = on_start
        self.on_stop  = on_stop
        self.on_clear = on_clear
        self.on_direction_change = on_direction_change
        self._throttle = {"tempo": None, "gate": None}


        # ── Transport buttons ─────────────────────────────────────
        # Start/Stop need to show “playing” state
        self.start_btn = tk.Button(self, text="Start", width=6,
                                   command=self._on_start_click)
        self.start_btn.pack(pady=2)

        self.stop_btn = tk.Button(self, text="Stop", width=6,
                                  command=self._on_stop_click)
        self.stop_btn.pack(pady=2)

        # Random and Clear remain the same
        self.random_btn = tk.Button(self, text="Random", width=6,
                                    command=on_random)
        self.random_btn.pack(pady=2)

        self.clear_btn = tk.Button(self, text="Clear All", width=6,
                           command=self._confirm_clear)
        self.clear_btn.pack(pady=2)


        # ── Sliders row (BPM, Gate, Subdivision + Direction) ─────
        slider_row = tk.Frame(self, bg=COLORS['bg'])
        slider_row.pack(pady=(8, 4))

        # BPM -----------------------------------------------------
        self.tempo_var = tk.IntVar(value=self.state.bpm)
        bpm_col = tk.Frame(slider_row, bg=COLORS['bg'])
        bpm_col.pack(side='left', padx=4)
        tk.Label(
            bpm_col,
            text="BPM",
            font=('Arial', 8),
            bg=COLORS['bg'],
            fg=COLORS['text']
        ).pack()
        tk.Scale(
            bpm_col,
            from_=240, to=40,
            orient='vertical',
            variable=self.tempo_var,
            length=112,
            showvalue=False,
            command=self._on_tempo_change
        ).pack()

        # BPM entry
        entry = tk.Entry(
            bpm_col,
            textvariable=self.tempo_var,
            width=5,
            justify='center'
        )
        entry.pack(pady=(4, 4))
        entry.bind('<Return>', lambda e: self._on_tempo_change(self.tempo_var.get()))

        # Keep state in sync even when value changes programmatically
        self.tempo_var.trace_add('write', lambda *args: self._on_tempo_change(self.tempo_var.get()))


        # Gate ----------------------------------------------------
        self.gate_var = tk.IntVar(value=self.state.gate_pct)  # use state value
        gate_col = tk.Frame(slider_row, bg=COLORS['bg'])
        gate_col.pack(side='left', padx=4)

        tk.Label(
            gate_col,
            text="GATE",
            font=('Arial', 8),
            bg=COLORS['bg'],
            fg=COLORS['text']
        ).pack()

        tk.Scale(
            gate_col,
            from_=100, to=10,
            orient='vertical',
            variable=self.gate_var,
            length=112,
            showvalue=False,
            command=self._on_gate_change  # ← add this line
        ).pack()

        tk.Entry(
            gate_col,
            textvariable=self.gate_var,
            width=5,
            justify='center'
        ).pack(pady=(4, 4))

        # ── Buttons row: Subdivision & Direction ─────────────────
        self.subdiv_var = tk.IntVar(value=DEFAULT_SUBDIVISION)
        buttons_row = tk.Frame(self, bg=COLORS['bg'])
        buttons_row.pack(pady=(4, 4))

        # Left sub-column: subdivision 1/4-1/32
        sub_col = tk.Frame(buttons_row, bg=COLORS['bg'])
        sub_col.pack(side='left', padx=2)
        for div in [4, 8, 16, 32]:
            b = tk.Button(
                sub_col,
                text=f"1/{div}",
                width=1,
                command=lambda d=div: self._set_subdivision(d)
            )
            b.pack(pady=2)
            if div == DEFAULT_SUBDIVISION:
                b.config(relief=tk.SUNKEN)
            setattr(self, f'subdiv_{div}', b)

        # Right sub-column: direction ⇒ ⇐ ⇄ ⇆
        dir_col = tk.Frame(buttons_row, bg=COLORS['bg'])
        dir_col.pack(side='left', padx=2)
        self.dir_buttons = []
        symbols = ["⇒", "⇐", "⇄", "⇆"]  # 0=Fwd,1=Rev,2=Ping,3=Rev-Ping
        for i, sym in enumerate(symbols):
            b = tk.Button(
                dir_col,
                text=sym,
                width=1,
                command=lambda m=i: self._set_direction(m)
            )
            b.pack(pady=2)
            self.dir_buttons.append(b)
        self._refresh_dir_buttons()

        # ── Icon (with slave toggle) ─────────────────────────
        try:
            default_img = Image.open(resource_path("assets/gord_icon.png")).resize((100, 100))
            slave_img   = Image.open(resource_path("assets/gord_icon_slave.png")).resize((100, 100))

            self.default_icon = ImageTk.PhotoImage(default_img)
            self.slave_icon   = ImageTk.PhotoImage(slave_img)

            self.icon_label = tk.Label(self, image=self.default_icon, bg=COLORS['bg'])
            self.icon_label.image = self.default_icon  # prevent garbage collection
            self.icon_label.pack(pady=(4, 4))
            self.icon_label.bind('<Double-Button-1>', self._on_slave_toggle)
        except Exception as e:
            print("⚠️ Icon load failed:", e)



        # ── Export panel ───────────────────────────────────────
        self.export_panel = ExportPanel(self, state)
        self.export_panel.pack(pady=(0, 10))
        
    def _debounced(self, key, ms, fn):
        """Coalesce rapid slider/entry updates."""
        prev = self._throttle.get(key)
        if prev is not None:
            try:
                self.after_cancel(prev)
            except Exception:
                pass
        self._throttle[key] = self.after(ms, fn)

        
    def _on_tempo_change(self, _val):
        def _apply():
            try:
                v = int(float(self.tempo_var.get()))
            except Exception:
                return
            self.state.bpm = max(1, min(400, v))
        self._debounced("tempo", 50, _apply)

    def _on_gate_change(self, _val):
        def _apply():
            try:
                g = int(float(self.gate_var.get()))
            except Exception:
                return
            self.state.gate_pct = max(1, min(100, g))
        self._debounced("gate", 50, _apply)


    def _on_start_click(self):
        # Always re-arm engine (push params/seq), even when slaved.
        self.on_start()

        # Only disable the Start button when *we* drive transport.
        if not self.get_slave_mode():
            self.start_btn.config(state=tk.DISABLED)




    def _on_stop_click(self):
        self.on_stop()
        self.start_btn.config(state=tk.NORMAL)


    # ── Subdivision helper
    def _set_subdivision(self, div):
        self.subdiv_var.set(div)
        self.state.subdivision = div   # ← THIS is the missing line!

        for d in [4, 8, 16, 32]:
            getattr(self, f'subdiv_{d}').config(
                relief=tk.SUNKEN if d == div else tk.RAISED
            )

    def _set_direction(self, mode):
        if mode in (2, 3):
            if self.state.direction_mode != mode:
                self.state.direction_mode = mode
                self.state.include_turnaround = False
            else:
                self.state.include_turnaround = not self.state.include_turnaround
        else:
            self.state.direction_mode = mode
            self.state.include_turnaround = True

        self._refresh_dir_buttons()
        if self.on_direction_change:
            self.on_direction_change()

    def _refresh_dir_buttons(self):
        for i, btn in enumerate(self.dir_buttons):
            if i == self.state.direction_mode:
                btn.config(relief=tk.SUNKEN)
                if i in (2, 3):
                    bg = 'lightgrey' if not self.state.include_turnaround else 'darkgrey'
                    btn.config(bg=bg)
                else:
                    btn.config(bg='SystemButtonFace')
            else:
                btn.config(relief=tk.RAISED, bg='SystemButtonFace')

    def _on_slave_toggle(self, event=None):
        self.state.slave_mode = not getattr(self.state, 'slave_mode', False)

        # always stop on toggle
        self.on_stop()

        # tell the daemon about the new mode WITHOUT starting transport
        if getattr(self.state, "midi_engine", None):
            self.state.midi_engine.update_slave(self.state.slave_mode)

        img = self.slave_icon if self.state.slave_mode else self.default_icon
        self.icon_label.config(image=img)


    # ── Public getters for MidiEngine / ExportPanel
    def get_tempo(self):
        self.state.bpm = max(1, self.tempo_var.get())
        return self.state.bpm


    def get_gate(self):
        return self.state.gate_pct  # safe to call from thread


    def get_subdivision(self):
        self.state.subdivision = self.subdiv_var.get()  # FORCE SYNC
        return self.subdiv_var.get()


    def get_slave_mode(self):
        return getattr(self.state, 'slave_mode', False)

    def update_export_buttons(self):
        self.export_panel.update_buttons()
        
    def _confirm_clear(self):
        popup = tk.Toplevel(self)
        popup.title("")
        popup.configure(bg=COLORS['bg'])
        popup.attributes('-topmost', True)
        popup.resizable(False, False)

        # Center popup on parent window (GORD main window)
        self.update_idletasks()  # Ensure geometry info is up to date
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 100
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 50
        popup.geometry(f"200x100+{x}+{y}")

        # Label
        tk.Label(
            popup,
            text="Are you sure?",
            font=("Arial", 10),
            fg=COLORS['text'],
            bg=COLORS['bg']
        ).pack(pady=(12, 8))

        # Buttons row
        btn_frame = tk.Frame(popup, bg=COLORS['bg'])
        btn_frame.pack(pady=(0, 8))

        yes_btn = tk.Button(
            btn_frame,
            text="Yes",
            width=8,
            command=lambda: (popup.destroy(), self._do_clear_all())
        )
        yes_btn.pack(side='left', padx=8)

        no_btn = tk.Button(
            btn_frame,
            text="No",
            width=8,
            command=popup.destroy
        )
        no_btn.pack(side='left', padx=8)

    def _do_clear_all(self):
        if self.on_clear:
            self.on_clear()
            
    def on_tick(self):
        if self.state.chain_mode_enabled and self.state.chain_runner and self.state.chain_runner.running:
            self.state.chain_runner.on_tick()
        else:
            # Normal SequenceGenerator step — if you already call it from here, leave it;
            # if your MidiEngine handles that, this can be empty
            pass


