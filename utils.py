# utils.py

import os
import sys
import tkinter as tk
from config import NOTE_NAMES, COLORS, NOTE_TO_COLOR
from theory import SCALES


# ── Resource Path (for PyInstaller) ──
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ── MIDI Clock Math ──
def pulses_per_step(div):
    return 24 * 4 // div  # e.g. div=4 (quarter) -> 24 pulses

# ── MIDI Utility ──
NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
def midi_to_name(midi):
    if midi is None:
        return "Rest"
    return f"{NOTE_NAMES[midi % 12]}{(midi // 12) - 1}"

def calc_scale_notes(root_name: str, scale_key: str) -> set[int]:
    """
    Return a {pitch-class} set for the chosen scale.
    root_name  = "C", "D#", etc.
    scale_key  = key into SCALES json (e.g. "major", "dorian").
    """
    if not root_name or not scale_key:
        return set()
    root_pc = NOTE_NAMES.index(root_name)
    ivs     = SCALES[scale_key]["intervals"]      # list of semitone offsets
    return {(root_pc + iv) % 12 for iv in ivs}

def snap_to_scale(note: int, allowed_pcs: set[int]) -> int:
    """Return the nearest in-scale MIDI note (search ±3 semitones)."""
    if not allowed_pcs or note % 12 in allowed_pcs:
        return note
    for delta in (1, -1, 2, -2, 3, -3):
        cand = note + delta
        if cand % 12 in allowed_pcs:
            return cand
    return note  # fallback: unchanged






def get_snapped_intervals_octaves(state):
    """
    Build {interval_index : {octave,…}} from the current sequence.

    • P1 (interval 0) and P8 (interval 12) are completely independent.
    • Same grid octave can exist in both iv=0 and iv=12.
    • Never convert or assume P8 just because it's a root note.
    """
    if not state.last_seq:
        return {}

    root_pc        = NOTE_NAMES.index(state.original_root)
    result         = {}

    for note in state.last_seq:
        if note is None:
            continue

        pc        = note % 12
        midi_oct  = note // 12
        grid_oct  = max(midi_oct - 1, 0)  # column number

        # ── Clean and minimal logic ───────────────────────────────
        if pc == root_pc:
            iv0_enabled = grid_oct in state.extension_octaves.get(0, set())
            iv12_enabled = grid_oct in state.extension_octaves.get(12, set())

            if iv0_enabled:
                result.setdefault(0, set()).add(grid_oct)
            if iv12_enabled:
                result.setdefault(12, set()).add(grid_oct)
        else:
            iv = (pc - root_pc) % 12
            result.setdefault(iv, set()).add(grid_oct)

    return result






# ── Color Utility ──
def lighten_color(color):
    if color.startswith('#'):
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    else:
        r16, g16, b16 = tk.Tk().winfo_rgb(color)
        r, g, b = r16 // 256, g16 // 256, b16 // 256
    return f"#{(r + 255) // 2:02x}{(g + 255) // 2:02x}{(b + 255) // 2:02x}"


def best_scales_for_notes(pcs, root_pc=None):
    """Return list of best matching scales as [(label string, root_pc)]."""
    matches = []
    input_set = set(pcs)

    # Tag MODES by convention — you can refine this list
    mode_keys = [k for k in SCALES if 'mode' in k.lower() or 'dorian' in k.lower()
                                          or 'phrygian' in k.lower()
                                          or 'lydian' in k.lower()
                                          or 'mixolydian' in k.lower()
                                          or 'aeolian' in k.lower()
                                          or 'locrian' in k.lower()]

    # Simple "pro scales" substrings → we boost these slightly in sort
    pro_scale_keywords = ['harmonic minor', 'melodic minor', 'altered', 'phrygian dom', 'phrygian dominant']

    for key, scale_def in SCALES.items():
        ivs = scale_def["intervals"]
        scale_notes = [(root_pc or 0) + iv for iv in ivs]
        scale_notes_pc = {n % 12 for n in scale_notes}

        covered      = len(input_set & scale_notes_pc)
        total_scale  = len(scale_notes_pc)
        coverage_pct = covered / total_scale if total_scale else 0

        # Classify match type
        if scale_notes_pc.issubset(input_set):
            match_type = 'EXACT'
            extra_notes = set()
        elif input_set.issubset(scale_notes_pc):
            match_type = 'SUB'
            extra_notes = scale_notes_pc - input_set
        else:
            match_type = 'PART'
            extra_notes = scale_notes_pc - input_set

        # Check if pro-scale
        display_name = scale_def.get('display_name', key)
        is_pro = any(s in display_name.lower() for s in pro_scale_keywords)

        matches.append((
            match_type, coverage_pct, len(extra_notes), total_scale,
            covered, display_name,
            (root_pc or 0) % 12, sorted(extra_notes),
            key in mode_keys,  # is_mode
            is_pro             # is_pro
        ))

    # Sort priority:
    match_priority = {'EXACT': 0, 'SUB': 1, 'PART': 2}

    # Split into groups for display order
    exact_sub = []
    part_non_mode = []
    part_mode = []

    matches.sort(key=lambda x: (
        match_priority[x[0]],
        -x[1],     # coverage_pct DESC
        -x[9],     # pro scales first when coverage is tied
        x[2],      # fewest extra notes ASC
        x[3]       # smallest scale first
    ))


    for m in matches:
        if m[0] == 'PART' and m[8]:  # PART and is mode
            part_mode.append(m)
        elif m[0] == 'PART':
            part_non_mode.append(m)
        else:
            exact_sub.append(m)

    # Build display
    result = []

    def add_to_result(group):
        for match_type, coverage_pct, num_extra, total_scale, covered, display_name, scale_root_pc, extra_notes, _, _ in group:
            if extra_notes:
                extra_str = " + " + " ".join(NOTE_NAMES[n] for n in extra_notes)
            else:
                extra_str = ""

            match_tag = f"[{match_type}]"
            label = f"{display_name} {match_tag}{extra_str}  {covered}/{total_scale}"
            result.append((label, scale_root_pc))

            if len(result) >= 6:
                break

    # Add in proper order
    add_to_result(exact_sub)
    if len(result) < 6:
        add_to_result(part_non_mode)
    if len(result) < 6:
        add_to_result(part_mode)

    return result


# ── Implied Chord Helper ──
def find_implied_chord(sel_mask, bass_pc, state):
    """Return name of implied chord (first best match), or None."""
    from theory import NOTE_NAMES, CHORDS

    pcs       = [i for i in range(12) if sel_mask & (1 << i)]
    sel_set   = set(pcs)
    N         = len(sel_set)
    user_root = getattr(state, "original_root", None)

    def pc_set(r, ivs):
        return {(r + iv) % 12 for iv in ivs}

    best = None
    best_score = -1

    for key, meta in CHORDS.items():
        if "alias_of" in meta or meta["length"] > N:
            continue
        ivs = meta["intervals"]

        for root in range(12):
            pcs_ch = pc_set(root, ivs)

            if not (pcs_ch.issubset(sel_set) or sel_set.issubset(pcs_ch)):
                continue

            matches = len(pcs_ch & sel_set)
            is_exact = (matches == len(pcs_ch) and matches == N)

            disp = (meta.get("display_name", key)
                       .replace("Diminished", "dim")
                       .replace("Augmented",  "aug")
                       .replace("Major",      "maj")
                       .replace("Minor",      "min"))

            name = NOTE_NAMES[root] + disp

            # Prefer EXACT > 7/7 > 6/7 > ... > 3/7 etc
            score = (10 if is_exact else 0) + matches

            # Bias toward user-selected root (if applicable)
            if NOTE_NAMES[root] == user_root:
                score += 3  # ← small but strong enough bias

            if score > best_score:
                best_score = score
                best = name

    return best

import tkinter as tk

class Tooltip:
    def __init__(self, widget, text, **kwargs):
        self.widget   = widget
        self._text_fn = text if callable(text) else (lambda: text)

        # Optional style overrides (None => keep old defaults below)
        self._bg   = kwargs.get("bg", None)
        self._fg   = kwargs.get("fg", None)
        self._font = kwargs.get("font", ("Fixedsys", 10))
        self._padx = kwargs.get("padx", 6)
        self._pady = kwargs.get("pady", 3)

        self._tip = None
        widget.bind("<Enter>",  self._enter,  add="+")
        widget.bind("<Leave>",  self._leave,  add="+")
        widget.bind("<Motion>", self._motion, add="+")

    def _enter(self, e):
        self._show(e.x_root + 12, e.y_root + 12)

    def _motion(self, e):
        if self._tip:
            self._tip.geometry(f"+{e.x_root + 12}+{e.y_root + 12}")

    def _leave(self, _):
        self._hide()

    def _show(self, x, y):
        self._hide()
        txt = self._text_fn() or ""
        if not txt:
            return

        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)

        # Defaults mirror previous behavior; overridden when kwargs provided
        bg = self._bg if self._bg is not None else "white"
        fg = self._fg if self._fg is not None else "black"

        frame = tk.Frame(self._tip, bg=bg, bd=1, relief="solid")
        frame.pack()
        label = tk.Label(frame, text=txt, bg=bg, fg=fg, font=self._font)
        label.pack(padx=self._padx, pady=self._pady)

        self._tip.geometry(f"+{x}+{y}")

    def _hide(self):
        try:
            if self._tip is not None:
                self._tip.destroy()
        finally:
            self._tip = None


class FancyTooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.waittime = delay  # in ms
        self.wraplength = 300  # pixels
        self.id = None
        self.tw = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)
        widget.bind("<ButtonPress>", self._leave)

    def _enter(self, event=None):
        self._schedule()

    def _leave(self, event=None):
        # Don't instantly hide — check if user just wobbled outside
        self.widget.after(100, self._check_leave)

    def _check_leave(self):
        # Defensive: if tipwindow attr not set yet, treat as no tipwindow
        if self.tw is None:
            return

        # Get mouse pointer location
        x, y = self.widget.winfo_pointerxy()
        widget_x = self.widget.winfo_rootx()
        widget_y = self.widget.winfo_rooty()
        widget_w = self.widget.winfo_width()
        widget_h = self.widget.winfo_height()

        # Define forgiveness zone in pixels
        forgiveness = 8  # You can adjust this

        if (widget_x - forgiveness <= x <= widget_x + widget_w + forgiveness and
            widget_y - forgiveness <= y <= widget_y + widget_h + forgiveness):
            # Mouse is still near widget → keep tooltip alive
            self.widget.after(100, self._check_leave)
        else:
            # Mouse moved away → hide
            self._unschedule()
            self._hide()



    def _schedule(self):
        self._unschedule()
        self.id = self.widget.after(self.waittime, self._show)

    def _unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def _show(self):
        if self.tw:
            return

        # Evaluate text
        text_lines = self.text() if callable(self.text) else self.text
        if isinstance(text_lines, str):
            text_lines = [(text_lines, COLORS['text'])]  # fallback if user passed just a string

        x, y, _, _ = self.widget.bbox("insert") if self.widget.bbox("insert") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        frame = tk.Frame(self.tw, bg="black", bd=0)
        frame.pack()

        for line, color in text_lines:
            # Split label at last space → "Name 3/7"
            if ' ' in line:
                prefix, counter = line.rsplit(' ', 1)
            else:
                prefix, counter = line, ""

            row = tk.Frame(frame, bg="black")
            row.pack(anchor='w')

            # If prefix contains ' + ' → this is a best_scales_for_notes style label
            if ' + ' in prefix:
                main_label, plus_part = prefix.split(' + ', 1)

                # Main label
                tk.Label(row, text=main_label + " ", justify='left',
                         font=("Fixedsys", 10), bg="black", fg=color,
                         anchor='w', padx=0, pady=0).pack(side='left')

                # Notes after +
                for note_str in plus_part.split():
                    note_color = NOTE_TO_COLOR.get(note_str, 'white')
                    tk.Label(row, text=note_str + " ", justify='left',
                             font=("Fixedsys", 10), bg="black", fg=note_color,
                             anchor='w', padx=0, pady=0).pack(side='left')

            else:
                # NORMAL LABEL → show as before (for interval nickname lists, etc.)
                tk.Label(row, text=prefix + " ", justify='left',
                         font=("Fixedsys", 10), bg="black", fg=color,
                         anchor='w', padx=0, pady=0).pack(side='left')

            if counter:
                tk.Label(row, text=counter, justify='left',
                         font=("Fixedsys", 10), bg="black", fg="white",
                         anchor='w', padx=0, pady=0).pack(side='left')



    def _hide(self):
        if self.tw:
            self.tw.destroy()
            self.tw = None
            





# ─── KeyMapper ───────────────────────────────────────────────────
class KeyMapper:
    """
    One diatonic “shape” (scale-degree offsets + octaves) frozen to the key
    that was active when Stay-In-Key was enabled.

        key_pc   – tonic of the locked key             (0-11)
        scale    – "major", "dorian", … (key in theory.SCALES)
        pattern  – [(deg_offset_from_root, octave), …]
    """
    def __init__(self, key_pc: int, scale: str, pattern):
        self.key_pc  = key_pc
        self.scale   = scale
        self.pattern = list(pattern)

    # ----------------------------------------------------------------
    @classmethod
    def from_grid(cls, state):
        if not (state.scale and state.selected_intervals):
            return None

        key_pc   = NOTE_NAMES.index(state.key_anchor)          # locked tonic
        root_pc  = NOTE_NAMES.index(state.original_root)       # live root
        ivs_key  = SCALES[state.scale]["intervals"]            # e.g. [0,2,4,5,7,9,11]
        key_pcs  = [(key_pc + iv) % 12 for iv in ivs_key]

        try:
            root_deg = key_pcs.index(root_pc)                  # degree of root
        except ValueError:
            return None

        pat = []
        for iv in sorted(state.selected_intervals):
            if iv in state.muted_intervals:
                continue

            note_pc = (root_pc + iv) % 12
            if note_pc not in key_pcs:
                continue                                        # out-of-key

            deg_off = (key_pcs.index(note_pc) - root_deg) % len(key_pcs)
            for octv in sorted(state.extension_octaves[iv]):
                pat.append((deg_off, octv))

        return cls(key_pc, state.scale, pat)

    # ----------------------------------------------------------------
    def transpose(self, new_root_name: str) -> list[int]:
        new_root_pc = NOTE_NAMES.index(new_root_name)
        ivs_key     = SCALES[self.scale]["intervals"]
        key_pcs     = [(self.key_pc + iv) % 12 for iv in ivs_key]

        # snap new root up to nearest in-key pc
        if new_root_pc in key_pcs:
            root_deg, oct_shift = key_pcs.index(new_root_pc), 0
        else:
            delta = 1
            while (new_root_pc + delta) % 12 not in key_pcs:
                delta += 1
            root_deg  = key_pcs.index((new_root_pc + delta) % 12)
            oct_shift = 1 if new_root_pc + delta >= 12 else 0

        notes = []
        for off, octv in self.pattern:
            pc = (self.key_pc + ivs_key[(root_deg + off) % len(ivs_key)]) % 12
            notes.append(((octv + oct_shift + 1) * 12) + pc)

        return notes


def interval_to_degree(iv: int, scale_key: str) -> int | None:
    """
    Map an interval-PC (0-11) to its 0-based degree index within the
    chosen scale.  Returns None if the interval isn’t in that scale.
    """
    if not scale_key:
        return None
    iv_mod = iv % 12
    for idx, scale_iv in enumerate(SCALES[scale_key]['intervals']):
        if scale_iv % 12 == iv_mod:
            return idx
    return None
