# fretboard.py

import tkinter as tk
from pathlib import Path
import json

from config import NOTES, NOTE_TO_COLOR, TUNINGS, SCALES, NUM_FRETS
from utils import note_index, shift_note, get_contrast_text_color

# Load chord definitions ------------------------------------------------------
with open(Path(__file__).parent / "chords.json", "r") as f:
    CHORDS = json.load(f)["chords"]


class Fretboard(tk.Frame):
    """Reusable 6‑string fretboard widget that *self‑heals* when certain
    attributes (mode / scale / chord) are missing from the shared AppState.

    The colouring rules are unified:
        • **Scale mode**   – every scale tone coloured, root underlined.
        • **Chord mode**   – chord tones coloured, root underlined.
        • **Raw‑note mode** (``state.mode`` is *None* or absent) – every
          passed‑in note coloured (all treated as chord‑tones) so FREDT
          launched via ``--notes`` behaves correctly.
    """

    # ---------------------------------------------------------------------
    def __init__(self, master, state):
        super().__init__(master, bg="#000")
        self.state = state
        self.fret_cells: list[list[tk.Label]] = []  # [string][fret]
        self._build_grid()

    # ------------------------------------------------------------------ UI ---
    def _build_grid(self):
        """Build the header + 6 × (NUM_FRETS + 1) label matrix."""
        # Clear any previous children (makes resetting simpler)
        for w in self.winfo_children():
            w.destroy()
        self.fret_cells.clear()

        # ── Fret‑number header row -------------------------------------
        marker_frets = {0, 3, 5, 7, 9, 12, 15, 17, 19, 21, 24}
        for f in range(NUM_FRETS + 1):
            fg = "#fff" if f in marker_frets else "#888"
            tk.Label(
                self, text=str(f), width=4, height=2,
                font=("Arial", 12, "bold"), bg="#111", fg=fg,
                relief="flat"
            ).grid(row=0, column=f, padx=1, pady=1, sticky="nsew")

        # ── Six‑string rows --------------------------------------------
        strings = TUNINGS[self.state.tuning]["strings"][::-1]  # low→high
        for s_idx, _ in enumerate(strings):
            row: list[tk.Label] = []
            for fret in range(NUM_FRETS + 1):
                lbl = tk.Label(
                    self, width=4, height=2,
                    font=("Arial", 12, "bold"),
                    relief="ridge", bd=1,
                    bg="#111", fg="#aaa"
                )
                lbl.grid(row=s_idx + 1, column=fret, padx=1, pady=1, sticky="nsew")
                row.append(lbl)
            self.fret_cells.append(row)

    # ------------------------------------------------------------ PAINTING ---
    def update_display(self):
        """Re‑compute colours anytime state changes, **safely** even if the
        hosting app’s ``AppState`` lacks mode/scale/chord attributes."""
        self.clear()

        # ── Pull attributes defensively --------------------------------
        mode        = getattr(self.state, "mode", None)
        scale_idx   = getattr(self.state, "scale", None)
        chord_idx   = getattr(self.state, "chord", None)
        chord_keys  = getattr(self.state, "chord_keys", [])
        root_pc     = getattr(self.state, "root", None) or 0  # fall back to C

        target_pcs: set[int]
        chord_pcs:  set[int] = set()

        # -------- Determine which pitch‑classes to highlight ------------
        if mode == "scale" and scale_idx is not None:
            scale_data = list(SCALES.values())[scale_idx]
            target_pcs = {(root_pc + iv) % 12 for iv in scale_data.get("intervals", [])}

        elif mode == "chord" and chord_idx is not None and chord_keys:
            key = chord_keys[chord_idx]
            ivs = CHORDS.get(key, {}).get("intervals", [])
            chord_pcs = {(root_pc + iv) % 12 for iv in ivs}
            target_pcs = chord_pcs

        else:  # Raw note‑set (FREDT launched via --notes or Build mode)
            raw = getattr(self, "notes_to_draw", None) or getattr(self.state, "selected_notes", [])
            target_pcs = {note_index(n) for n in raw}
            chord_pcs  = target_pcs  # treat every selected note as a chord‑tone

        # -------- Colour the grid --------------------------------------
        strings = TUNINGS[self.state.tuning]["strings"][::-1]
        for s_idx, open_note in enumerate(strings):
            for fret in range(NUM_FRETS + 1):
                lbl = self.fret_cells[s_idx][fret]
                note = shift_note(open_note, fret)
                pc = note_index(note)

                if pc in target_pcs:
                    bg = NOTE_TO_COLOR[note]
                    fg = get_contrast_text_color(bg)
                    style = ("Arial", 12, "bold", "underline") if pc == root_pc else ("Arial", 12, "bold")
                    lbl.config(text=note, bg=bg, fg=fg, font=style)
                else:
                    lbl.config(text=note, bg="#000000", fg="#444444", font=("Arial", 12, "bold"))

    # ---------------------------------------------------------------- UTIL ---
    def clear(self):
        """Reset the board to the neutral dark‑grey grid."""
        for row in self.fret_cells:
            for lbl in row:
                note = lbl.cget("text") or ""  # preserve displayed letter if any
                lbl.config(text=note, bg="#111", fg="#444", font=("Arial", 12, "bold"))
