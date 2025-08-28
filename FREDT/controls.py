# controls.py

import tkinter as tk
from tkinter import ttk
from config import NOTES, SCALES, TUNINGS
import json
from pathlib import Path

with open(Path(__file__).parent / "chords.json", "r") as f:
    CHORDS = json.load(f)["chords"]

class ControlPanel(tk.Frame):
    def __init__(self, master, state, on_change, defer_init=False):
        super().__init__(master, bg="#111")
        self.state = state
        self.on_change = on_change  # callback to update fretboard

        self.root_var   = tk.StringVar()
        self.scale_keys = list(SCALES.keys())
        self.scale_labels = [SCALES[k]["display_name"] for k in self.scale_keys]
        self.scale_var = tk.StringVar()
        self.chord_keys = [k for k in CHORDS if "intervals" in CHORDS[k]]
        state.chord_keys = self.chord_keys
        self.chord_labels = [CHORDS[k]["display_name"] for k in self.chord_keys]
        self.chord_var = tk.StringVar()
        self.tuning_var = tk.StringVar()

        # ── NEW: always mirror the state's tuning in the box ──
        self.tuning_var.set(TUNINGS[state.tuning]['name'])

        # Only apply other defaults if we didn’t get CLI args
        if not defer_init:
            self.root_var.set("C")
            self.scale_var.set(self.scale_labels[0])
            self.chord_var.set(self.chord_labels[0])

        self._build_ui()


    def _build_ui(self):
        self.columnconfigure((0, 1, 2, 3), weight=1)

        # Store label references for later highlighting
        self.lbl_scale = self._make_dropdown("Scale", self.scale_labels, self.scale_var, self._on_scale_change, 1)
        self.lbl_chord = self._make_dropdown("Chord", self.chord_labels, self.chord_var, self._on_chord_change, 2)

        self._make_dropdown("Root", NOTES, self.root_var, self._on_root_change, 0)
        self._make_dropdown("Tuning", [t["name"] for t in TUNINGS], self.tuning_var, self._on_tuning_change, 3)

        self._highlight_active_mode("scale, chord")  # default


    def _make_dropdown(self, label, options, variable, command, col):
        frame = tk.Frame(self, bg="#111")
        frame.grid(row=0, column=col, padx=10, sticky="ew")
        frame.columnconfigure(0, weight=1)

        lbl = tk.Label(frame, text=label, fg="#fff", bg="#111")
        lbl.grid(row=0, column=0, sticky="w")

        combo = ttk.Combobox(
            frame,
            values=options,
            textvariable=variable,
            state="readonly",
            font=("Segoe UI", 10),
        )
        combo.grid(row=1, column=0, sticky="nsew", pady=(2, 0))
        combo.bind("<<ComboboxSelected>>", lambda e: command(variable.get()))
        return lbl  # return the label so it can be updated later


    def _on_root_change(self, val):
        idx = NOTES.index(val)
        self.state.update(root=idx)
        self.on_change()


    def _on_scale_change(self, val):
        idx = self.scale_labels.index(val)
        self.state.update(scale=idx, chord=None, mode="scale")
        self._highlight_active_mode("scale")
        self.on_change()


    def _on_tuning_change(self, selected_name):
        tuning_names = [t["name"] for t in TUNINGS]
        idx = tuning_names.index(selected_name)
        self.state.update(tuning=idx, mode=self.state.mode)
        self.on_change()
        
    def _on_chord_change(self, val):
        idx = self.chord_labels.index(val)
        self.state.update(chord=idx, scale=None, mode="chord")
        self._highlight_active_mode("chord")
        self.on_change()
        
    def _highlight_active_mode(self, mode):
        if mode == "scale":
            self.lbl_scale.config(fg="#ffffff")
            self.lbl_chord.config(fg="#666666")
        elif mode == "chord":
            self.lbl_scale.config(fg="#666666")
            self.lbl_chord.config(fg="#ffffff")



