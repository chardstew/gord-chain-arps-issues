import sys, os
import json
import argparse
from pathlib import Path
import tkinter as tk
from tkinter import font
import importlib.util
import os

def resource_path(relative_path):
    """ Get absolute path to resource (for PyInstaller or dev) """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# Core config and app logic
from config import COLORS, TUNINGS, NOTES, NOTE_TO_COLOR
from utils import get_contrast_text_color
from state import AppState
from controls import ControlPanel
from fretboard import Fretboard

# Load chord data from JSON (if needed externally)
with open(Path(__file__).parent / "chords.json", "r") as f:
    CHORDS = json.load(f)["chords"]

# Load theory.py safely
theory_path = Path(__file__).parent / "theory.py"
spec = importlib.util.spec_from_file_location("theory", theory_path)
theory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theory)

SCALES = theory.SCALES
CHORDS = theory.CHORDS

def main():
    root = tk.Tk()

    # --- cross-platform app icon ---
    ico = resource_path("../assets/gord_icon.ico")
    png = resource_path("../assets/gord_icon.png")
    try:
        if sys.platform == "win32" and os.path.exists(ico):
            # Windows accepts .ico; no 'default=' kw
            root.iconbitmap(ico)
        else:
            # macOS/Linux: use iconphoto with PNG
            _icon_png = tk.PhotoImage(file=png)
            root.iconphoto(True, _icon_png)
            root._icon_png = _icon_png  # keep a ref to avoid GC
    except Exception:
        pass
    
    # --- CLI args from GORD ---
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="")
    parser.add_argument("--notes", default="")   # comma-separated: C,Eb,G
    args = parser.parse_args()
    incoming_root  = args.root or None
    incoming_notes = [s.strip() for s in args.notes.split(",") if s.strip()]
    
        # --- main container + state ---
    root.configure(bg=COLORS['bg'])
    frame = tk.Frame(root, bg=COLORS['bg'])
    frame.grid(row=0, column=0, sticky="n")

    state = AppState()


    def update():
        # Sync selected_notes to fretboard explicitly
        if state.mode is None:                       # no scale / chord selected
            fretboard.notes_to_draw = list(state.selected_notes)
        elif hasattr(fretboard, "notes_to_draw"):    # clear the helper when not used
            delattr(fretboard, "notes_to_draw")
        fretboard.update_display()
        update_status_text()

    # Controls with defer_init based on CLI usage
    defer = bool(incoming_notes)
    controls = ControlPanel(frame, state, update, defer_init=defer)
    controls.grid(row=0, column=0, sticky="ew", pady=8)
    state.chord_keys = controls.chord_keys
    state.scale_keys = controls.scale_keys


    # Fretboard and status area
    fretboard_container = tk.Frame(frame, bg=COLORS['bg'])
    fretboard_container.grid(row=1, column=0, sticky="n", pady=12)
    frame.grid_rowconfigure(1, weight=1)

    global fretboard
    fretboard = Fretboard(fretboard_container, state)
    fretboard.pack(padx=12)

    status_frame = tk.Frame(frame, bg=COLORS['bg'])
    status_frame.grid(row=2, column=0, pady=(12, 8))

    status_inverted = False
    def toggle_status_colors():
        nonlocal status_inverted
        status_inverted = not status_inverted
        for child in status_frame.winfo_children():
            if status_inverted:
                child.config(bg="#000", fg="#fff")
            else:
                note = child.cget("text")
                bg = NOTE_TO_COLOR.get(note, "#111")
                fg = get_contrast_text_color(bg)
                is_root = (note == NOTES[state.root])
                child.config(
                    bg=bg,
                    fg=fg,
                    font=("Arial", 12, "bold", "underline") if is_root else ("Arial", 12, "bold")
                )

    def update_status_text():
        notes = []
        if state.mode == "scale" and state.scale is not None:
            intervals = list(SCALES.values())[state.scale]["intervals"]
            notes = [(NOTES[(state.root + i) % 12], i == 0) for i in intervals]
        elif state.mode == "chord" and state.chord is not None:
            key = state.chord_keys[state.chord]
            intervals = CHORDS.get(key, {}).get("intervals", [])
            notes = [(NOTES[(state.root + i) % 12], i == 0) for i in intervals]

        for widget in status_frame.winfo_children():
            widget.destroy()

        for note_name, is_root in notes:
            bg = NOTE_TO_COLOR[note_name]
            fg = get_contrast_text_color(bg)
            font_style = ("Arial", 12, "bold", "underline") if is_root else ("Arial", 12, "bold")
            cell = tk.Label(
                status_frame, text=note_name, bg=bg, fg=fg,
                width=4, height=2, font=font_style,
                relief="ridge", bd=1, padx=4, pady=2
            )
            cell.pack(side="left", padx=2)
            cell.bind("<Button-1>", lambda e: toggle_status_colors())


    # ── Apply CLI args AFTER controls + fretboard exist ─────────────────
    if incoming_notes:
        # 1) basic root + note set
        state.selected_notes = set(incoming_notes)
        state.root = NOTES.index(incoming_root)
        controls.root_var.set(incoming_root)
        
        state.mode  = None          # disable scale / chord colouring
        state.scale = None
        state.chord = None

        # 2) identify matching chord or scale
        pcs = sorted((NOTES.index(n) - state.root) % 12 for n in incoming_notes)

        # --- CHORD match ----------------------------------------------
        matched = False
        pcs_set = set(pcs)                # unique pitch-classes (0-11)

        for key, meta in CHORDS.items():
            meta_set = {i % 12 for i in meta["intervals"]}   # 14 → 2
            if meta_set == pcs_set:
                idx = controls.chord_keys.index(key)
                controls.chord_var.set(controls.chord_labels[idx])
                controls._on_chord_change(controls.chord_labels[idx])
                controls.scale_var.set("")        # clear scale box
                matched = True
                break

        # --- SCALE match (only if no chord) --------------------------------------
        if not matched:
            for key, meta in SCALES.items():
                if sorted(meta["intervals"]) == pcs:
                    idx = controls.scale_keys.index(key)      # <- real position
                    controls.scale_var.set(controls.scale_labels[idx])        # was scale_keys
                    controls._on_scale_change(controls.scale_labels[idx])     # same here
                    controls.chord_var.set("")                # clear chord box
                    break


        # 3) final redraw now that EVERY widget exists
        update()




    def do_reset():
        state.reset()
        state.chord_keys = controls.chord_keys
        controls.root_var.set("C")
        controls.scale_var.set("Major")
        controls.chord_var.set(controls.chord_labels[0])
        controls.tuning_var.set(TUNINGS[0]['name'])
        fretboard.clear()
        for widget in status_frame.winfo_children():
            widget.destroy()
        update()

    reset_btn = tk.Button(
        frame, text="Reset", font=("Arial", 12, "bold"),
        bg="white", fg="black",
        activebackground="#e6e6e6", activeforeground="black",
        highlightthickness=0, borderwidth=2, relief="raised",
        command=do_reset
    )

    reset_btn.grid(row=3, column=0, sticky="n", padx=20, pady=(0, 16))


    root.mainloop()

if __name__ == "__main__":
    main()
