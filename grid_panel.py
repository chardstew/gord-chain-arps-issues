# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 1/5 — imports, class init, and NEW _build_grid (pixel/grid sizing)
# ─────────────────────────────────────────────────────────────────────────────
import tkinter as tk
import sys
from config import (
    COLORS, NOTE_NAMES, NOTE_TO_COLOR, MAX_OCTAVE,
    CELL_WIDTH, CELL_HEIGHT, CELL_PAD,
    INTERVAL_LABELS, INTERVAL_NICKNAMES, ENHARMONIC
)
from chain_arps import ChainArpsWindow
from utils import Tooltip, FancyTooltip, get_snapped_intervals_octaves, \
                  best_scales_for_notes, snap_to_scale, find_implied_chord
from theory import CHORDS, get_scale_keys, get_chord_keys
from collections import defaultdict
from pathlib import Path
import json
with open(Path(__file__).parent / "scales.json", "r") as f:
    SCALES = json.load(f)["scales"]


class IntervalGridPanel(tk.Frame):
    def __init__(self, master, state, midi_engine, on_change):
        super().__init__(master, bg=COLORS['bg'])
        self.state = state
        self.midi_engine = midi_engine
        self.on_change = on_change
        self.note_frames = {}   # NEW: wrappers that carry the colored border
        self.note_labels = {}
        self.interval_buttons = {}
        self.octave_buttons = {}

        self.notes_button = None
        self.notes_label = None

        self.cheatsheet_active = False
        self.cheatsheet_intervals = []

        self._build_grid()
        self.update_grid()
        self.update_notes_row()
        self._init_cheat_menu()
        
        
    def _toggle_oct(self, iv, o):
        # make sure our containers exist and iv has a set
        self._ensure_collections(iv)

        octs = self.state.extension_octaves[iv]
        if o in octs:
            octs.remove(o)
        else:
            octs.add(o)

        # keep selected_intervals in sync with whether the row has any active octaves
        if octs:
            self.state.selected_intervals.add(iv)
        else:
            self.state.selected_intervals.discard(iv)

        # maintain Stay-In-Key snapshot if active
        if self.state.diatonic_mode and getattr(self.state, "stay_in_key", False):
            from utils import KeyMapper
            self.state.key_mapper = KeyMapper.from_grid(self.state)

        # propagate changes
        self.on_change()
        if getattr(self.state, "build_mode_enabled", False) and hasattr(self.master, "_sync_build_to_state"):
            self.master._sync_build_to_state()


    def _ensure_collections(self, iv=None):
        # selected_intervals must be a set
        if isinstance(getattr(self.state, "selected_intervals", None), list):
            self.state.selected_intervals = set(self.state.selected_intervals)
        elif not hasattr(self.state, "selected_intervals") or self.state.selected_intervals is None:
            self.state.selected_intervals = set()

        # extension_octaves must be dict[int->set[int]]
        if not isinstance(getattr(self.state, "extension_octaves", None), dict):
            self.state.extension_octaves = {}

        if iv is not None:
            v = self.state.extension_octaves.get(iv)
            if v is None:
                self.state.extension_octaves[iv] = set()
            elif isinstance(v, list):
                self.state.extension_octaves[iv] = set(v)



    def _build_grid(self):
        grid = tk.Frame(self, bg=COLORS['bg'])
        grid.pack(anchor='w')

        # Fonts
        self._font_small = ("Fixedsys", 10)
        self._font_med   = ("Fixedsys", 12)
        self._font_big   = ("Fixedsys", 18)

        # Optional helper (keep or remove if unused)
        def btn_opts():
            return dict(
                font=self._font_small,
                highlightthickness=0,
                takefocus=False,
                bd=1,
                bg="#E0E0E0",
                fg="black",
                activebackground="#CFCFCF",
                activeforeground="black"
            )

        # Pixel sizing
        SCALE   = 0.65 if sys.platform == "darwin" else 1.0
        CELL_PX = max(22, int(30 * SCALE))
        self._cell_px = CELL_PX
        self._font_notes = ("Fixedsys", max(10, int(self._cell_px * 0.82)))

        STICKY = "nsew"

        # ----- Column sizing (square cells) -----
        grid.grid_columnconfigure(0, minsize=CELL_PX * 2, weight=0)   # Note label wider
        grid.grid_columnconfigure(1, minsize=CELL_PX,       weight=0) # Int
        for c in range(2, 2 + MAX_OCTAVE + 1):                        # Octaves
            grid.grid_columnconfigure(c, minsize=CELL_PX, weight=0)
        grid.grid_columnconfigure(2 + MAX_OCTAVE + 1, minsize=CELL_PX, weight=0)  # L
        grid.grid_columnconfigure(2 + MAX_OCTAVE + 2, minsize=CELL_PX, weight=0)  # R

        # ----- Row sizing -----
        grid.grid_rowconfigure(0,  minsize=int(CELL_PX * 0.65), weight=0)  # header
        for r in range(1, 14):
            grid.grid_rowconfigure(r, minsize=CELL_PX, weight=0)            # 13 square rows
        grid.grid_rowconfigure(14, minsize=CELL_PX, weight=0)               # notes row

        # =======================
        # Header row (row = 0)
        # =======================
        self.note_label = tk.Label(grid, text="Note", font=self._font_small,
                                   bg=COLORS['bg'], fg=COLORS['text'])
        self.note_label.grid(row=0, column=0, padx=CELL_PAD, pady=2, sticky=STICKY)
        Tooltip(self.note_label, lambda: self.state.last_selection_label or "Choose Scale/Chord")

        tk.Label(grid, text="Int", font=self._font_small, bg=COLORS['bg'], fg=COLORS['text']) \
            .grid(row=0, column=1, padx=CELL_PAD, sticky=STICKY)

        for o in range(MAX_OCTAVE + 1):
            tk.Label(grid, text=str(o), font=self._font_small, bg=COLORS['bg'], fg=COLORS['text']) \
                .grid(row=0, column=2 + o, sticky=STICKY)

        tk.Label(grid, text="L", font=self._font_small, bg=COLORS['bg'], fg=COLORS['text']) \
            .grid(row=0, column=MAX_OCTAVE + 3, padx=CELL_PAD, sticky=STICKY)
        tk.Label(grid, text="R", font=self._font_small, bg=COLORS['bg'], fg=COLORS['text']) \
            .grid(row=0, column=MAX_OCTAVE + 4, padx=CELL_PAD, sticky=STICKY)

        for child in grid.grid_slaves(row=0):
            child.bind("<Double-1>", lambda e: self._open_channel_popup())

        # =======================
        # Interval rows (1..13)
        # =======================
        for iv in range(13):
            r = iv + 1

            # NEW: wrapper frame = the colored border; inner label = text, sits on bg
            wrap = tk.Frame(grid, bg=COLORS['bg'])                         # border carrier
            wrap.grid(row=r, column=0, padx=CELL_PAD, pady=1, sticky=STICKY)
            lbl = tk.Label(wrap, text="–", font=self._font_small,
                           bg=COLORS['bg'], fg=COLORS['text'],
                           bd=0, relief='flat', highlightthickness=0, takefocus=0)
            lbl.pack(expand=True, fill='both', padx=1, pady=1)             # 1-px border
            self.note_frames[iv] = wrap
            self.note_labels[iv] = lbl
            # click anywhere (label or border) opens the tools menu
            wrap.bind("<Button-1>", self._show_tools_menu)
            lbl.bind("<Button-1>", self._show_tools_menu)

            ib = tk.Label(grid, text=INTERVAL_LABELS[iv],
                          width=4, height=2, relief='ridge', bd=1,
                          bg='white', fg='black',
                          font=self._font_small, cursor='hand2')
            ib.grid(row=r, column=1, padx=1, pady=1)
            ib.bind('<Button-1>', lambda e, iv=iv: self._toggle_interval(iv))
            self.interval_buttons[iv] = ib
            Tooltip(ib, INTERVAL_NICKNAMES.get(iv, ""))

            self.octave_buttons[iv] = []
            for o in range(MAX_OCTAVE + 1):
                ob = tk.Label(grid, text=str(o),
                              width=4, height=2, bg='white',
                              relief='ridge', bd=1, font=self._font_small)
                ob.grid(row=r, column=2 + o, padx=1, pady=1)
                ob.bind("<Button-1>", lambda e, iv=iv, o=o: self._toggle_oct(iv, o))
                self.octave_buttons[iv].append(ob)

            lbl_left = tk.Label(grid, text='←', width=4, height=2,
                                relief='ridge', bd=1, bg='white', fg='black',
                                font=self._font_small, cursor='hand2')
            lbl_left.grid(row=r, column=MAX_OCTAVE + 3, padx=1, pady=1)
            lbl_left.bind('<Button-1>', lambda e, iv=iv: self._shift(iv, -1))

            lbl_right = tk.Label(grid, text='→', width=4, height=2,
                                 relief='ridge', bd=1, bg='white', fg='black',
                                 font=self._font_small, cursor='hand2')
            lbl_right.grid(row=r, column=MAX_OCTAVE + 4, padx=1, pady=1)
            lbl_right.bind('<Button-1>', lambda e, iv=iv: self._shift(iv, +1))

        # =======================
        # Notes row (row = 14)
        # =======================
        notes_r = 14
        self.notes_container = tk.Frame(grid, bg=COLORS['bg'], height=self._cell_px)
        self.notes_container.grid(row=notes_r, column=1,
                                  columnspan=MAX_OCTAVE + 2,
                                  sticky=STICKY, padx=CELL_PAD, pady=0)
        self.notes_container.grid_propagate(False)

        arrow_opts = dict(width=4, height=2, relief="ridge", bd=1,
                          bg="white", fg="black",
                          font=self._font_small, cursor="hand2")

        btn_left  = tk.Label(grid, text="⇇", **arrow_opts)
        btn_left.grid(row=notes_r, column=MAX_OCTAVE + 3, padx=1, pady=1)
        btn_left.bind("<Button-1>", lambda e: self._shift_all(-1))

        btn_right = tk.Label(grid, text="⇉", **arrow_opts)
        btn_right.grid(row=notes_r, column=MAX_OCTAVE + 4, padx=1, pady=1)
        btn_right.bind("<Button-1>", lambda e: self._shift_all(+1))






# Add tooltip to notes row with Best Scales
    def _notes_tooltip_text(self):
        notes = self.state.display_notes or []
        if not notes:
            return []

        pcs = [NOTE_NAMES.index(n) for n in notes if n in NOTE_NAMES]
        root_pc = NOTE_NAMES.index(self.state.original_root) if getattr(self.state, "original_root", None) in NOTE_NAMES else 0

        matches = best_scales_for_notes(pcs, root_pc)

        # Return list of (text, color)
        result = []
        # Try to get implied chord
        sel_mask, bass_pc, root_note, voicing = self._make_mask_and_bass()
        implied = find_implied_chord(sel_mask, bass_pc, self.state)
        if implied:
            result.append((f"Implied Chord: {implied}", COLORS['highlight']))

        for label, scale_root_pc in matches:
            color = NOTE_TO_COLOR.get(NOTE_NAMES[scale_root_pc], COLORS['text'])
            result.append((label, color))

        return result




    def _toggle_interval(self, iv):
        if iv in self.state.muted_intervals:
            self.state.muted_intervals.remove(iv)
        else:
            self.state.muted_intervals.add(iv)
            self.state.selected_intervals.add(iv)
        if self.state.diatonic_mode and self.state.stay_in_key:
            from utils import KeyMapper
            self.state.key_mapper = KeyMapper.from_grid(self.state)

        self.on_change()
        if self.state.build_mode_enabled and hasattr(self.master, "_sync_build_to_state"):
            self.master._sync_build_to_state()





    def _shift(self, iv, delta):
        self._ensure_collections(iv)
        octs = self.state.extension_octaves[iv]
        shifted = {(o + delta) % (MAX_OCTAVE + 1) for o in octs}
        self.state.extension_octaves[iv] = shifted
        if shifted:
            self.state.selected_intervals.add(iv)
        else:
            self.state.selected_intervals.discard(iv)
        if self.state.diatonic_mode and self.state.stay_in_key:
            from utils import KeyMapper
            self.state.key_mapper = KeyMapper.from_grid(self.state)
        self.on_change()
        if self.state.build_mode_enabled and hasattr(self.master, "_sync_build_to_state"):
            self.master._sync_build_to_state()

    def _shift_all(self, delta):
        # ensure all existing values are sets
        for iv in list(self.state.extension_octaves.keys()):
            self._ensure_collections(iv)
        for iv, octs in self.state.extension_octaves.items():
            shifted = {(o + delta) % (MAX_OCTAVE + 1) for o in octs}
            self.state.extension_octaves[iv] = shifted
            if shifted:
                self.state.selected_intervals.add(iv)
            else:
                self.state.selected_intervals.discard(iv)
        if self.state.diatonic_mode and self.state.stay_in_key:
            from utils import KeyMapper
            self.state.key_mapper = KeyMapper.from_grid(self.state)
        self.on_change()
        if self.state.build_mode_enabled and hasattr(self.master, "_sync_build_to_state"):
            self.master._sync_build_to_state()




    def update_grid(self):
        root = next(iter(self.state.selected_notes)) if self.state.selected_notes else None

        for iv in range(13):
            # Set note label text + color
            if not self.state.selected_notes:
                txt = "–"
                note_color = COLORS['text']
                base_note = None
            else:
                idx = (NOTE_NAMES.index(root) + iv) % 12
                enh = ENHARMONIC[idx]
                txt = enh.split("/")[1] if self.state.use_flats and "/" in enh else enh.split("/")[0]
                base_note = NOTE_NAMES[idx]
                note_color = NOTE_TO_COLOR.get(base_note, COLORS['text'])

            # Only text/fg here; frame color handled in _refresh_overlays
            self.note_labels[iv].config(text=txt, fg=note_color, font=self._font_small, bg=COLORS['bg'])

            # Interval button visual — ALWAYS note color; gray ONLY when muted
            ib = self.interval_buttons[iv]

            # Determine base note for this row even if nothing is selected
            bn = base_note
            if bn is None:
                fallback_root = getattr(self.state, "original_root", None)
                if fallback_root in NOTE_NAMES:
                    idx_fb = (NOTE_NAMES.index(fallback_root) + iv) % 12
                    bn = NOTE_NAMES[idx_fb]

            if iv in self.state.muted_intervals:
                ib_bg = "#E0E0E0"                 # muted → gray
            else:
                ib_bg = NOTE_TO_COLOR.get(bn, "#E0E0E0")  # always the note color

            ib.config(bg=ib_bg, fg="black")


            # Octave cells
            for o, ob in enumerate(self.octave_buttons[iv]):
                self._ensure_collections(iv)
                active = (o in self.state.extension_octaves[iv])

                color = (
                    'lightgray' if iv in self.state.muted_intervals
                    else NOTE_TO_COLOR.get(base_note, COLORS['button'])
                ) if active else 'white'

                ob.config(bg=color, fg='black')




        # Refresh highlight borders after text/colors
        self._refresh_overlays()



    def update_notes_row(self):
        # Clear previous widgets
        for child in self.notes_container.winfo_children():
            child.destroy()

        # 1) Build unique note list from current sequence (with optional snapping)
        seq = self.state.last_seq or []
        if (self.state.diatonic_mode and not self.state.stay_in_key and self.state.scale_notes):
            seq = [snap_to_scale(n, self.state.scale_notes) if n is not None else None for n in seq]

        seen = set()
        names = []
        for n in seq:
            if n is None:
                continue
            idx = n % 12
            enh = ENHARMONIC[idx]
            disp_name = enh.split("/")[1] if self.state.use_flats and "/" in enh else enh.split("/")[0]
            if disp_name not in seen:
                seen.add(disp_name)
                names.append((disp_name, NOTE_NAMES[idx]))
                if len(names) >= 12:
                    break
        self.state.display_notes = [n[1] for n in names]

        # 2) Render as a single horizontal row, centered in the fixed-height container
        inner = tk.Frame(self.notes_container, bg=COLORS['bg'])
        inner.pack(expand=True, fill='both')     # <-- fill so it takes the row’s box
        # DO NOT call pack_propagate(False) here

        row = tk.Frame(inner, bg=COLORS['bg'])
        row.pack(expand=True)                    # <-- centers the whole strip horizontally

        row.bind('<Button-1>', self._show_notes_menu)

        for label, base in names:
            col = NOTE_TO_COLOR.get(base, COLORS['text'])
            lbl = tk.Label(row, text=label, font=self._font_notes, bg=COLORS['bg'], fg=col)
            lbl.pack(side='left', padx=(0, CELL_PAD))
            lbl.bind('<Button-1>', self._show_notes_menu)



        FancyTooltip(self.notes_container, lambda: self._notes_tooltip_text())



    def _show_notes_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg="black", fg="white",
                       font=("Fixedsys", 10), borderwidth=2, relief="solid")
        menu.add_command(label="CHXRD", command=self._open_inspector)
        menu.add_command(label="FREDT", command=self._open_fredt)

        try:
            # Simple → stable → downward popup → no flicker
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

            
    # ----------------------------------------------------------------------
    # grid_panel.py  –  replace the whole _open_fredt() body
    def _open_fredt(self):
        from config import NOTE_NAMES
        from utils import resource_path
        import subprocess, sys, os

        # ── build note list (unchanged) ───────────────────────────────
        seq   = getattr(self.state, "last_seq", [])
        pcs   = {n % 12 for n in seq if n is not None} if seq else set()
        notes = [NOTE_NAMES[pc] for pc in sorted(pcs)] or sorted(self.state.selected_notes)
        if not notes:
            return
        root_name = getattr(self.state, "original_root", None) or notes[0]

        fredt_py = resource_path("FREDT/fredt_main.py")
        if not os.path.exists(fredt_py):
            print("⚠️  fredt_main.py not found")
            return

        # ── **here is the only line that changed** ──
        python_exe = "pythonw" if getattr(sys, "frozen", False) else sys.executable
        # --------------------------------------------

        subprocess.Popen(
            [python_exe, fredt_py, "--root", root_name, "--notes", ",".join(notes)],
            cwd=os.path.dirname(fredt_py),
            creationflags=(
                subprocess.CREATE_NO_WINDOW        # still suppresses if python.exe used
                if sys.platform == "win32" else 0
            )
        )


    # ─────────────────────────────────────────────────────────────

    def _refresh_overlays(self):
        """Colour the left-hand note labels with frames that always match."""
        # determine the current root index safely
        root = next(iter(self.state.selected_notes), None)
        if root in NOTE_NAMES:
            root_idx = NOTE_NAMES.index(root)
        else:
            # fall back to original_root if set; otherwise 0
            fallback = getattr(self.state, "original_root", None)
            root_idx = NOTE_NAMES.index(fallback) if fallback in NOTE_NAMES else 0

        # --- decide which pitch-classes get a frame --------------------
        if self.cheatsheet_active:
            # while Stay-In-Key is on, lock to key_anchor; otherwise follow original root
            anchor_name = (
                self.state.key_anchor
                if (self.state.stay_in_key and getattr(self.state, "key_anchor", None))
                else getattr(self.state, "original_root", None)
            )
            if anchor_name not in NOTE_NAMES:
                anchor_name = NOTE_NAMES[root_idx]
            anchor_pc = NOTE_NAMES.index(anchor_name)
            frame_pcs = {(anchor_pc + iv) % 12 for iv in self.cheatsheet_intervals}

        elif self.state.stay_in_key and getattr(self.state, "scale", None):
            anchor_name = self.state.key_anchor or getattr(self.state, "original_root", None)
            if anchor_name not in NOTE_NAMES:
                anchor_name = NOTE_NAMES[root_idx]
            anchor_pc = NOTE_NAMES.index(anchor_name)
            ivs = SCALES[self.state.scale]["intervals"]
            frame_pcs = {(anchor_pc + iv) % 12 for iv in ivs}

        elif self.state.diatonic_mode and getattr(self.state, "scale", None):
            # Plain diatonic mode → frame current root + scale
            anchor_pc = NOTE_NAMES.index(root) if root in NOTE_NAMES else 0
            ivs = SCALES[self.state.scale]["intervals"]
            frame_pcs = {(anchor_pc + iv) % 12 for iv in ivs}

        else:
            frame_pcs = set()  # no frames

        # --- paint each row --------------------------------------------
        for iv, lbl in self.note_labels.items():
            row_pc = (root_idx + iv) % 12
            base_note = NOTE_NAMES[row_pc]
            colour = NOTE_TO_COLOR.get(base_note, COLORS['highlight'])
            show = (row_pc in frame_pcs)

            # keep label text synced with PC; draw consistent frame
            wrap = self.note_frames[iv]
            lbl  = self.note_labels[iv]

            show   = (row_pc in frame_pcs)
            colour = NOTE_TO_COLOR.get(base_note, COLORS['highlight'])

            # border = wrapper bg; inner label stays on app bg
            wrap.config(bg=(colour if show else COLORS['bg']))
            lbl.config(
                text=base_note,
                bg=COLORS['bg'],
                fg=NOTE_TO_COLOR.get(base_note, COLORS['text']),
                font=getattr(self, "_font_small", ("Fixedsys", 10))
            )



    def _init_cheat_menu(self):
        # Primary right-click cheat menu
        self.cheat_menu = tk.Menu(self, tearoff=0)
        self.cheat_menu.add_command(label="Clear", command=self._clear_cheat)

        # Scales submenu (use JSON order)
        scale_sub = tk.Menu(self.cheat_menu, tearoff=0)
        for key in list(SCALES.keys()):
            display = SCALES[key]['display_name']
            scale_sub.add_command(label=display, command=lambda k=key: self._apply_cheat('scale', k))
        self.cheat_menu.add_cascade(label="Scales", menu=scale_sub)

        # Chords submenu
        chord_sub = tk.Menu(self.cheat_menu, tearoff=0)
        for key in get_chord_keys():
            display = CHORDS[key]['display_name']
            chord_sub.add_command(label=display, command=lambda k=key: self._apply_cheat('chord', k))
        self.cheat_menu.add_cascade(label="Chords", menu=chord_sub)

        # Bind the NOTE header label to pop the menu
        self.note_label.bind("<Button-1>", lambda e: self.cheat_menu.tk_popup(e.x_root, e.y_root))


    def _apply_cheat(self, kind, key):
        """Apply a scale/chord cheatsheet overlay and (for scales) set scale notes."""
        self.cheatsheet_active = True
        src = SCALES if kind == 'scale' else CHORDS
        self.cheatsheet_intervals = [iv % 12 for iv in src[key]['intervals']]
        self.state.last_selection_label = src[key]['display_name']

        if kind == 'scale':
            self.state.scale = key
            ivs = SCALES[key]["intervals"]
            # anchor to key if locked, else original root, else C
            anchor_name = (
                self.state.key_anchor
                or getattr(self.state, "original_root", None)
                or "C"
            )
            if anchor_name not in NOTE_NAMES:
                anchor_name = "C"
            tpc = NOTE_NAMES.index(anchor_name)
            self.state.scale_notes = {(tpc + iv) % 12 for iv in ivs}
        else:
            # chord overlay shouldn't force scale filtering
            self.state.scale = None
            self.state.scale_notes.clear()

        self._refresh_overlays()
        self.on_change()


    def _clear_cheat(self):
        """Clear the scale/chord cheat overlay and reset related modes."""
        self.cheatsheet_active = False
        self.cheatsheet_intervals = []

        # clear any scale filtering
        self.state.scale = None
        self.state.scale_notes.clear()
        self.state.last_selection_label = ""

        # fully exit Diatonic + Stay-In-Key (if they were on)
        self.state.diatonic_mode = False
        self.state.stay_in_key = False
        self.state.key_mapper = None
        self.state.key_anchor = None

        self._refresh_overlays()
        self.on_change()

        
    # ─────────────────────────────────────────────────────────────
    def _make_mask_and_bass(self):
        """Return mask, bass_pc, root_note, voiced interval list."""
        seq = [n for n in self.state.last_seq if n is not None]
        if not seq:
            return 0, None, None, []

        root_pc = NOTE_NAMES.index(self.state.original_root)
        notes = sorted(seq)  # ascending MIDI order

        mask = 0
        for n in notes:
            mask |= 1 << (n % 12)

        # Try to find the lowest played note that matches the root pitch class
        root_note = next((n for n in notes if n % 12 == root_pc), None)
        root_pc_int = NOTE_NAMES.index(self.state.original_root)      # 0-11
        if root_pc_int in {n % 12 for n in notes}:
            bass_pc = root_pc_int

        else:
            bass_pc = notes[0] % 12

        # Interval from root PC (wrapped to 0–11)
        def iv(n): return (n % 12 - root_pc) % 12

        voicing = [(n, iv(n)) for n in notes]

        return mask, bass_pc, root_note, voicing
    
    

    # ─────────────────────────────────────────────────────────────────────────────
    def _open_channel_popup(self):
        popup = tk.Toplevel(self)
        popup.title("MIDI Setup")
        popup.configure(bg=COLORS['bg'])
        popup.attributes('-topmost', True)
        popup.resizable(False, False)

        # Header
        tk.Label(
            popup,
            text="Assign MIDI Channels to Octaves",
            font=("Fixedsys", 14),
            fg=COLORS['highlight'],
            bg=COLORS['bg']
        ).pack(pady=(10, 4))

        frame = tk.Frame(popup, bg=COLORS['bg'])
        frame.pack(padx=12, pady=4)

        # Channel dropdowns per octave
        self._octave_dropdowns = {}
        for octv in range(9):
            row = tk.Frame(frame, bg=COLORS['bg'])
            row.pack(anchor='w')

            tk.Label(
                row, text=f"Octave {octv}:",
                font=("Fixedsys", 12), width=12,
                bg=COLORS['bg'], fg=COLORS['text']
            ).pack(side='left')

            var = tk.StringVar()
            current = self.state.octave_channel_map.get(octv, "")
            if current:
                var.set(str(current))
            self._octave_dropdowns[octv] = var

            dropdown = tk.OptionMenu(row, var, *[""] + [str(i) for i in range(1, 17)])
            dropdown.config(
                font=("Fixedsys", 12),
                bg=COLORS['bg'],
                fg=COLORS['text'],
                width=4,
                highlightthickness=0,
                activebackground=COLORS['bg'],
                activeforeground=COLORS['highlight'],
                indicatoron=False
            )
            dropdown["menu"].config(font=("Fixedsys", 12), bg="black", fg="white")
            dropdown.pack(side='left', padx=(4, 0))

        # OK / Cancel buttons
        btns = tk.Frame(popup, bg=COLORS['bg'])
        btns.pack(pady=(8, 12))

        def apply_and_close():
            new_map = {}
            for o, var in self._octave_dropdowns.items():
                val = var.get().strip()
                if val.isdigit():
                    ch = int(val)
                    if 1 <= ch <= 16:
                        new_map[o] = ch
            self.state.octave_channel_map = new_map
            self.state.routing_mode = "octave"
            popup.destroy()

        def cancel():
            popup.destroy()

        tk.Button(
            btns, text="OK", font=("Fixedsys", 12),
            command=apply_and_close,
            bg=COLORS['button'], fg=COLORS['text'],
            activebackground=COLORS['highlight']
        ).pack(side='left', padx=8)

        tk.Button(
            btns, text="Cancel", font=("Fixedsys", 12),
            command=cancel,
            bg=COLORS['button'], fg=COLORS['text'],
            activebackground=COLORS['highlight']
        ).pack(side='left', padx=8)


    # Note-column popup: Diatonic toggle + Chain Arps launcher
    def _show_tools_menu(self, event):
        m = tk.Menu(self, tearoff=0, bg="black", fg="white", font=("Fixedsys", 10))

        has_scale = bool(getattr(self.state, "scale", None))
        on_dia    = bool(self.state.diatonic_mode)
        on_sik    = bool(getattr(self.state, "stay_in_key", False))

        # Diatonic
        label_d = "Diatonic Mode  ✓" if on_dia else "Diatonic Mode"
        m.add_command(
            label=label_d,
            command=self._toggle_diatonic_mode,
            state=(tk.NORMAL if has_scale and not on_sik else (tk.DISABLED if not has_scale else tk.NORMAL))
        )

        # Stay In Key
        label_k = "Stay In Key  ✓" if on_sik else "Stay In Key"
        m.add_command(
            label=label_k,
            command=self._toggle_stay_in_key,
            state=(tk.NORMAL if has_scale else tk.DISABLED)
        )

        m.add_command(label="Chain Arps…", command=self._open_chain_arps)

        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()


    # Stay-In-Key toggle — minimal but functional
    def _toggle_stay_in_key(self):
        if not getattr(self.state, "scale", None):
            return
        self.state.stay_in_key = not self.state.stay_in_key
        if self.state.stay_in_key:
            self.state.diatonic_mode = True
            self.state.key_anchor    = self.state.original_root
        else:
            self.state.key_anchor = None
            self.state.key_mapper = None
        self.on_change()


    def _toggle_diatonic_mode(self):
        if not getattr(self.state, "scale", None):
            return
        if self.state.stay_in_key and self.state.diatonic_mode:
            return
        self.state.diatonic_mode = not self.state.diatonic_mode
        self.on_change()
        # avoid sticky menu focus on mac
        try:
            self.cheat_menu.grab_release()
        except Exception:
            pass


    def _open_chain_arps(self):
        ChainArpsWindow(self.master, self.state, self.midi_engine, self.on_change)


    def _open_inspector(self, *_):
        mask, bass_pc, root_note, voicing = self._make_mask_and_bass()
        if mask:
            if not hasattr(self, '_inspector'):
                self._inspector = self._Inspector(self)
            self._inspector.show_for(mask, bass_pc)
           
           

            # ─────────────────────────────────────────────────────────────────────────────
    # BLOCK 5/5 — Inspector popup (contiguous: full class)
    # ─────────────────────────────────────────────────────────────────────────────
    class _Inspector(tk.Toplevel):
        """Popup: coloured notes header + 2-column chord list."""
        def __init__(self, parent):
            super().__init__(parent)
            self.title("CHXRD")
            self.withdraw()
            self.configure(bg=COLORS['bg'])
            self.attributes('-topmost', True)
            self.protocol("WM_DELETE_WINDOW", self.withdraw)
            self.bind('<Escape>', lambda e: self.withdraw())

            # Create the header first, so it's available to dragging & close button
            self.hdr = tk.Frame(self, bg=COLORS['bg'])
            self.hdr.pack(pady=(6, 4))

            self.make_draggable()
            self.make_close_button()

            # scrolling region
            self.scroll_outer = tk.Frame(self, bg=COLORS['bg'])
            self.scroll_outer.pack(fill='both', expand=True)

            self.canvas = tk.Canvas(self.scroll_outer, bg=COLORS['bg'],
                                    highlightthickness=0)
            self.canvas.pack(side='left', fill='both', expand=True)

            self.scrollbar = tk.Scrollbar(self.scroll_outer, orient='vertical',
                                          command=self.canvas.yview)
            self.scrollbar.pack(side='right', fill='y')
            self.canvas.configure(yscrollcommand=self.scrollbar.set)

            self.inner = tk.Frame(self.canvas, bg=COLORS['bg'])
            self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
            self.inner.bind(
                '<Configure>',
                lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            )
            # Enable scrolling via trackpad or mouse wheel
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)   # Windows + macOS
            self.canvas.bind_all("<Button-4>", self._on_mousewheel)     # Linux scroll up
            self.canvas.bind_all("<Button-5>", self._on_mousewheel)     # Linux scroll down

        # ── helper: turn intervals → note names (bass-pc first) ──────────
        def _spell(self, root_pc, ivs, bass_pc=None):
            from config import NOTE_TO_COLOR, NOTE_NAMES
            pcs = [(root_pc + iv) % 12 for iv in ivs]
            if bass_pc in pcs:
                while pcs[0] != bass_pc:
                    pcs = pcs[1:] + pcs[:1]

            frame = tk.Frame(self.inner, bg=COLORS['bg'])
            for pc in pcs:
                name = NOTE_NAMES[pc]
                col = NOTE_TO_COLOR.get(name, COLORS['text'])
                tk.Label(frame, text=name, font=("Fixedsys", 18, "normal"),
                         bg=COLORS['bg'], fg=col).pack(side='left', padx=2)
            return frame

        # ── public entry point ───────────────────────────────────────────
        def show_for(self, sel_mask, bass_pc):
            notes, chord_rows = self._identify(sel_mask, bass_pc)

            # ---- rebuild header ----
            for w in self.hdr.winfo_children():
                w.destroy()
            for n in notes:
                col = NOTE_TO_COLOR.get(n, COLORS['text'])
                tk.Label(self.hdr, text=n, font=("Fixedsys", 18, 'bold'),
                         bg=COLORS['bg'], fg=col).pack(side='left', padx=4)

            # ---- clear previous list ----
            for w in self.inner.winfo_children():
                w.destroy()

            # ---- two columns inside ‘inner’ ----
            left  = tk.Frame(self.inner, bg=COLORS['bg'])
            right = tk.Frame(self.inner, bg=COLORS['bg'])
            left.grid(row=0, column=0, sticky='nw')
            right.grid(row=0, column=1, sticky='nw', padx=(12, 0))

            # ---- populate ----
            for row in chord_rows:
                if "header" in row:
                    tk.Label(left, text=row["header"],
                             font=("Fixedsys", 18, 'bold'),
                             bg=COLORS['bg'], fg=COLORS['text']
                    ).pack(anchor='w')
                    tk.Label(right, text="", font=("Fixedsys", 18),
                             bg=COLORS['bg'], fg=COLORS['text']
                    ).pack(anchor='w')
                    continue  # headers only

                # Only runs for real chord rows
                root_note = NOTE_NAMES[row["root_pc"]]
                fg_color = NOTE_TO_COLOR.get(root_note, COLORS['text']) if row.get("bass_pc") is None else COLORS['text']

                tk.Label(left, text=row["name"],
                         font=("Fixedsys", 18),
                         bg=COLORS['bg'], fg=fg_color
                ).pack(anchor='w')

                self._spell(row["root_pc"], row["intervals"], row.get("bass_pc")).pack(in_=right, anchor='w')

            # centre the popup
            w, h = 400, 400
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{w}x{h}+{sw//2-w//2}+{sh//2-h//2}")
            self.deiconify()

        # ── identify chords & bucket them ───────────────────────────────
        def _identify(self, sel_mask, bass_pc):
            from theory import NOTE_NAMES, CHORDS
            from collections import defaultdict

            pcs       = [i for i in range(12) if sel_mask & (1 << i)]
            sel_set   = set(pcs)
            N         = len(sel_set)
            user_root = getattr(self.master.state, "original_root", None)

            # ── helpers ──────────────────────────────────────────────
            def pc_set(r, ivs):            # root-pc → set of chord pcs
                return {(r + iv) % 12 for iv in ivs}

            def inversion_sort_key(d):     # order inversions by distance
                root = d["root_pc"]
                bass = d.get("bass_pc", root)
                try:
                    return d["intervals"].index((bass - root) % 12)
                except ValueError:
                    return 99

            # ── build buckets (EXACT, 7/7, 6/7 …) ───────────────────
            buckets = defaultdict(list)
            seen    = set()

            for key, meta in CHORDS.items():
                if "alias_of" in meta or meta["length"] > N:
                    continue
                ivs = meta["intervals"]

                for root in range(12):
                    pcs_ch = pc_set(root, ivs)
                    missing = pcs_ch - sel_set       # chord notes not played
                    # allow either exact/full match or selection subset of a chord
                    if not (pcs_ch.issubset(sel_set) or sel_set.issubset(pcs_ch)):
                        continue

                    # detect a “no5” case (selection ⊆ chord and only 5th is missing)
                    fifth_pc = (root + 7) % 12
                    no5 = sel_set.issubset(pcs_ch) and missing == {fifth_pc}

                    # build display name (compact)
                    disp = (meta.get("display_name", key)
                               .replace("Diminished", "dim")
                               .replace("Augmented",  "aug")
                               .replace("Major",      "maj")
                               .replace("Minor",      "min"))
                    if no5:
                        disp += "no5"

                    base = NOTE_NAMES[root] + disp
                    for bass in pcs_ch:
                        name = base if bass == root else f"{base}/{NOTE_NAMES[bass]}"
                        if name in seen:
                            continue
                        seen.add(name)

                        matches = len(pcs_ch)
                        tag     = ("EXACT" if matches == N and NOTE_NAMES[root] == user_root
                                   else f"{matches}/{N}")

                        buckets[tag].append({
                            "name":      name,
                            "root_pc":   root,
                            "bass_pc":   bass if bass != root else None,
                            "intervals": ivs,
                            "chord_type": key
                        })

            # ——— determine the note‐header order from the first EXACT match ———
            if "EXACT" in buckets and buckets["EXACT"]:
                first = buckets["EXACT"][0]
                ivs   = first["intervals"]
                root0 = first["root_pc"]
                seen_pcs  = set()
                header_pcs = []
                for iv in ivs:                        # in the JSON’s interval order
                    pc = (root0 + iv) % 12
                    if pc not in seen_pcs:
                        seen_pcs.add(pc)
                        header_pcs.append(pc)
            else:
                header_pcs = [i for i in range(12) if sel_mask & (1 << i)]

            # ── decide tag order & golden root list ─────────────────
            order = ["EXACT", f"{N}/{N}"] + [
                f"{k}/{N}" for k in range(N-1, 2, -1) if f"{k}/{N}" in buckets
            ]

            main_chord_keys = []
            if buckets.get("EXACT"):
                for chord in buckets["EXACT"]:
                    key = (chord["chord_type"], chord["root_pc"])
                    if key not in main_chord_keys:
                        main_chord_keys.append(key)

            # ── helper to order roots & inversions inside a bucket ──
            def order_root_then_inversions(items):
                by_root = defaultdict(list)
                for d in items:
                    key = (d["chord_type"], d["root_pc"])
                    by_root[key].append(d)

                ordered = []
                # 1) golden root order
                for key in main_chord_keys:
                    if key not in by_root:
                        continue
                    group = by_root.pop(key)
                    roots      = [g for g in group if g["bass_pc"] is None]
                    inversions = [g for g in group if g["bass_pc"] is not None]
                    inversions.sort(key=inversion_sort_key)
                    ordered.extend(roots + inversions)

                # 2) leftovers → keep chord-types grouped, order by header_pcs
                left_groups = list(by_root.values())

                def group_root(group):
                    return next(d for d in group if d["bass_pc"] is None)

                left_groups.sort(
                    key=lambda grp: header_pcs.index(group_root(grp)["root_pc"])
                )

                for group in left_groups:
                    roots      = [g for g in group if g["bass_pc"] is None]
                    inversions = [g for g in group if g["bass_pc"] is not None]
                    inversions.sort(key=inversion_sort_key)
                    ordered.extend(roots + inversions)

                return ordered

            # ── build final rows list ───────────────────────────────
            rows = []

            # Implied chord block (first EXACT if available)
            implied_list = order_root_then_inversions(buckets["EXACT"]) if "EXACT" in buckets else []
            if not implied_list and "EXACT" in buckets:
                implied_list = buckets["EXACT"]   # fallback: raw bucket

            rows.append({"header": "Implied Chord"})
            if implied_list:
                rows.append(implied_list[0])
            else:
                rows.append({"header": "(no exact match)"})
            rows.append({"header": ""})  # spacer

            # Then normal buckets
            for tag in order:
                if tag not in buckets:
                    continue
                rows.append({"header": f"[{tag}]"})
                rows.extend(order_root_then_inversions(buckets[tag]))
                rows.append({"header": ""})      # blank spacer

            return [NOTE_NAMES[p] for p in header_pcs], rows

        def make_draggable(self):
            def start_move(event):
                self._drag_start = (event.x_root, event.y_root)

            def do_move(event):
                dx = event.x_root - self._drag_start[0]
                dy = event.y_root - self._drag_start[1]
                x = self.winfo_x() + dx
                y = self.winfo_y() + dy
                self.geometry(f"+{x}+{y}")
                self._drag_start = (event.x_root, event.y_root)

            self.hdr.bind("<Button-1>", start_move)
            self.hdr.bind("<B1-Motion>", do_move)

        def make_close_button(self):
            close_btn = tk.Button(
                self.hdr, text="✕", font=("Fixedsys", 14),
                bg=COLORS['bg'], fg=COLORS['text'],
                relief='flat', bd=0, highlightthickness=0,
                activebackground=COLORS['bg'],
                activeforeground=COLORS['highlight'],
                command=self.withdraw
            )
            close_btn.pack(side='right', padx=8)

        def _on_mousewheel(self, event):
            if event.num == 4:        # Linux scroll up
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:      # Linux scroll down
                self.canvas.yview_scroll(1, "units")
            else:                      # Windows/macOS (delta is +/-120 or higher)
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
