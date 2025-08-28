# export_panel.py

import tkinter as tk
from config import COLORS, NOTE_NAMES
from export import choose_export_folder, export_arp_sequence, export_chord_sequence

class ExportPanel(tk.Frame):
    def __init__(self, master, state):
        super().__init__(master, bg=COLORS['bg'])
        self.state = state
        self.dest_folder = None

        # Export buttons
        self.arp_btn = tk.Button(self, text="Get Arp", width=7, state='normal',
                                 command=self.get_arp)
        self.arp_btn.pack(pady=2)

        self.chord_btn = tk.Button(self, text="Get Chord", width=7, state='normal',
                                   command=self.get_chord)
        self.chord_btn.pack(pady=2)

        self.update_buttons()

    def update_buttons(self):
    
        #Enable export buttons if either:
        # • we’re in Build mode (the user is constructing a pattern), OR
        # • state.last_seq already holds notes to export. 
        enable = self.state.build_mode_enabled or bool(self.state.last_seq)

        new_state = 'normal' if enable else 'disabled'
        self.arp_btn.config(  state=new_state)
        self.chord_btn.config(state=new_state)


    def _ensure_folder(self):
        if not self.dest_folder:
            folder = choose_export_folder()
            if folder:
                self.dest_folder = folder

    def get_arp(self):
        self._ensure_folder()
        if not self.dest_folder:
            return
        
        self.state.subdivision = self.master.subdiv_var.get()

        export_arp_sequence(
            seq=self.state.last_seq,
            bpm=self.state.bpm,
            gate_pct=self.state.gate_pct,
            subdivision=self.state.subdivision,
            dest_folder=self.dest_folder
        )

    def get_chord(self):
        self._ensure_folder()
        if not self.dest_folder:
            return

        chord_notes = []
        if self.state.selected_notes and self.state.selected_intervals:
            root = next(iter(self.state.selected_notes))
            for iv in sorted(self.state.selected_intervals):
                if iv in self.state.muted_intervals:
                    continue
                for o in self.state.extension_octaves[iv]:
                    midi = NOTE_NAMES.index(root) + iv + 12 * o
                    chord_notes.append(midi)

        if chord_notes:
            export_chord_sequence(
                chord_notes,
                bpm=self.state.bpm,
                dest_folder=self.dest_folder
            )
