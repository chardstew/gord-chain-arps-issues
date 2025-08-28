# sequence_panel.py

import tkinter as tk
from config import COLORS, ENHARMONIC, NOTE_NAMES, NOTE_TO_COLOR
from piano_panel import PianoPanel
from utils import Tooltip
from sequence_engine import SequenceGenerator
from utils import Tooltip, get_snapped_intervals_octaves, snap_to_scale
from config import COLORS, ENHARMONIC, NOTE_NAMES, NOTE_TO_COLOR, CELL_WIDTH, CELL_HEIGHT, CELL_PAD



class SequencePanel(tk.Frame):
    def __init__(self, master, state, on_note_play=None, on_state_change=None, on_stop=None):
        super().__init__(master, bg=COLORS['bg'])
        self.state = state
        self.on_note_play = on_note_play
        self.on_state_change = on_state_change
        self.on_stop = on_stop
        self.seq_labels = []
        self.build_labels = []

        self._build_ui()
        # Populate UI (and counters) with the default sequence right away:
        self.on_get_default(toggle_mode=False)
        
    # helper at top of SequencePanel
    def _midi_to_oct(self, midi):      # MIDI 0 ⇒ -1, 60 ⇒ 4
        return str(midi // 12 - 1)


    def _sync_build_to_state(self):
        seq = []
        for lbl in self.build_labels:
            if getattr(lbl, 'disabled', False):
                continue
            if getattr(lbl, 'rest', False):
                seq.append(None)
            elif lbl.note_midi is not None:
                seq.append(lbl.note_midi)
        self.state.last_seq = seq


    def _build_ui(self):
        # ── Piano on top ─────────────────────────────────────────
        self.piano = PianoPanel(self, self.state, self._on_piano_click)
        self.piano.pack(pady=(0, 7))

        # ── Container for grids and buttons ───────────────────────
        stack = tk.Frame(self, bg=COLORS['bg'])
        stack.pack()

        # ========= TOP 8×4 GRID =================================
        top_grid = self._add_grid(stack, self.seq_labels, is_left=True)
        top_grid.pack()

        # Button row under top grid
        btn_row1 = tk.Frame(stack, bg=COLORS['bg'])
        btn_row1.pack(fill='x', pady=(4, 4))

        self.pull_btn = tk.Button(btn_row1, text="Pull In", width=10,
                             command=self.on_get_default)
        self.pull_btn.pack(side='left')

        self.alt_btn = tk.Button(btn_row1, text="Alt Seq", width=10,
                                 command=self.on_alt_seq)
        self.alt_btn.pack(side='right')

        # ── Root & Counters Row with fixed layout and pixel alignment ───────
        root_row = tk.Frame(stack, bg=COLORS['bg'])
        root_row.pack(pady=(0, 4), fill='x')

        # Grid layout with fixed-size containers
        root_row.columnconfigure(0, minsize=80)  # matches "Pull In"
        root_row.columnconfigure(1, weight=1)    # center flex
        root_row.columnconfigure(2, minsize=80)  # matches "Alt Seq"
        root_row.grid_rowconfigure(0, minsize=64)

        # Left counter frame
        left_frame = tk.Frame(root_row, width=64, height=64, bg=COLORS['bg'])
        left_frame.grid(row=0, column=0)
        left_frame.pack_propagate(False)

        # Center root frame
        center_frame = tk.Frame(root_row, width=64, height=64, bg=COLORS['bg'])
        center_frame.grid(row=0, column=1)
        center_frame.pack_propagate(False)

        # Right counter frame
        right_frame = tk.Frame(root_row, width=64, height=64, bg=COLORS['bg'])
        right_frame.grid(row=0, column=2)
        right_frame.pack_propagate(False)

        # LEFT: Unique note count
        self.count_unique_lbl = tk.Label(
            left_frame,
            text="0",
            font=("Fixedsys", 18),
            bg=COLORS['bg'],
            fg="white",
            anchor='center',
            justify='center'
        )
        self.count_unique_lbl.pack(expand=True)
        Tooltip(self.count_unique_lbl, "Distinct Notes")

        # CENTER: Root label
        self.root_label = tk.Label(
            center_frame,
            text=self.state.original_root,
            font=("Fixedsys", 28),
            bg=COLORS['bg'],
            fg=NOTE_TO_COLOR.get(self.state.original_root, COLORS['text']),
            width=2,
            anchor='center',
            justify='center',
            highlightthickness=3,
            highlightbackground=NOTE_TO_COLOR.get(self.state.original_root, COLORS['text']),
            highlightcolor=NOTE_TO_COLOR.get(self.state.original_root, COLORS['text'])
        )
        self.root_label.pack(expand=True)
        self.root_label.bind("<Button-1>", lambda e: self._toggle_enharmonic())

        # RIGHT: Total note count
        self.count_total_lbl = tk.Label(
            right_frame,
            text="0",
            font=("Fixedsys", 18),
            bg=COLORS['bg'],
            fg="white",
            anchor='center',
            justify='center'
        )
        self.count_total_lbl.pack(expand=True)
        Tooltip(self.count_total_lbl, "Total Notes") 



        # ========= BOTTOM 8×4 GRID ===============================
        btn_row2 = tk.Frame(stack, bg=COLORS['bg'])
        btn_row2.pack(fill='x', pady=(0, 4))

        self.build_btn = tk.Button(btn_row2, text="Build", width=10,
                                   command=self.on_build)
        self.build_btn.pack(side='left')

        clear_btn = tk.Button(btn_row2, text="Clear", width=10,
                              command=self.on_clear)
        clear_btn.pack(side='right')

        bottom_grid = self._add_grid(stack, self.build_labels, is_left=False)
        bottom_grid.pack()

        # keep Alt/Build button relief in sync at start
        self._refresh_mode_buttons()



    def _add_grid(self, parent, label_list, is_left):
        grid = tk.Frame(parent, bg=COLORS['bg'])

        CELL_FONT = ("Fixedsys", 10)  # match IntervalGridPanel cell font

        for r in range(4):
            for c in range(8):
                i = r * 8 + c
                lbl = tk.Label(
                    grid,
                    text="",
                    width=4, height=2,          # char units
                    bg="white",
                    relief="ridge",
                    bd=1,
                    font=CELL_FONT              # <<< key line for uniform sizing
                )
                lbl.grid(row=r, column=c, padx=1, pady=1)

                # keep your metadata
                lbl.note_midi = None
                lbl.rest = False
                lbl.disabled = False

                # keep your bindings
                if is_left:
                    lbl.bind("<Button-1>", lambda e, i=i: self.on_left_single(i))
                    lbl.bind("<Double-1>", lambda e, i=i: self.on_left_double(i))
                else:
                    lbl.bind("<Button-1>", lambda e, i=i: self.on_right_single(i))
                    lbl.bind("<Double-1>", lambda e, i=i: self.on_right_double(i))

                label_list.append(lbl)

        return grid

            
    def _toggle_enharmonic(self):
        self.state.use_flats = not self.state.use_flats
        if self.on_state_change:
            self.on_state_change()



    def on_get_default(self, toggle_mode: bool = True):
        """
        Pull In button.
        • If Build mode is ON  → just mirror the Build grid (notes + rests).
        • Otherwise            → regenerate using the single engine source of truth.
        """
        # Build-mode: mirror the Build grid
        if self.state.build_mode_enabled:
            if not self.state.alt_seq_enabled:
                self.state.seq_mode = 0
            self._sync_build_to_state()
            self._transpose_build_sequence()
            seq = self.state.last_seq
            self._render_sequence(seq)
            self.update_counters()
            return

        # SINGLE SOURCE OF TRUTH (includes alt + direction)
        base = SequenceGenerator(self.state).get_sequence_list()

        # Wrap vs one-pass (unchanged behavior)
        if toggle_mode:
            self.state.seq_mode = 1 - self.state.seq_mode

        if self.state.seq_mode == 0:
            seq = []
            while len(seq) < 32 and base:
                seq.extend(base)
            seq = seq[:32]
        else:
            seq = base

        # Commit & render
        self.state.last_seq = seq
        self._render_sequence(seq)
        self.update_counters()

# ------------------------------------------------------------
    # Refresh the left pull-in grid WITHOUT toggling modes
    # ------------------------------------------------------------
    def refresh_left_grid(self):
        """
        Re-populate the left (pull-in) grid using the CURRENT
        pull-in mode and the latest state.last_seq.
        """
        if hasattr(self, "_populate_left_onepass") and self.pull_in_mode == 0:
            self._populate_left_onepass()        # one-pass view
        elif hasattr(self, "_populate_left_32") and self.pull_in_mode == 1:
            self._populate_left_32()             # 32-step view
        elif hasattr(self, "on_get_default"):     # older builds
            self.on_get_default()                # respect current mode


    def on_alt_seq(self):
        # Toggle Alt-Seq builder (preserve wrap vs single-pass mode)
        self.state.alt_seq_enabled = not self.state.alt_seq_enabled
        self._refresh_mode_buttons()
        self.on_get_default(toggle_mode=False)

    def _weave_alt(self):
        from itertools import zip_longest

        # 1) build one list per interval
        lists = []
        if not self.state.selected_notes:
            return []

        root = next(iter(self.state.selected_notes))
        for iv in sorted(self.state.selected_intervals):
            if iv in self.state.muted_intervals:
                continue
            octs = sorted(self.state.extension_octaves.get(iv, []))
            seq = [
                SequenceGenerator(self.state)._midi_from_grid(root, iv, o)
                for o in octs
            ]
            if seq:
                lists.append(seq)

        if not lists:
            return []  # ⬅ safe early exit to avoid crash

        # 2) weave by cycling each list (wrap-around) for max rounds
        result = []
        max_len = max(len(l) for l in lists)
        for i in range(max_len):
            for l in lists:
                result.append(l[i % len(l)])
        return result




            
    def _render_sequence(self, seq):
        if self.state.diatonic_mode and self.state.scale_notes:
            snap_map = get_snapped_intervals_octaves(self.state)
            # Build snapped version of seq:
            snapped_seq = []
            for note in seq:
                if note is None:
                    snapped_seq.append(None)
                else:
                    snapped_seq.append(snap_to_scale(note, self.state.scale_notes))
            seq = snapped_seq
        for i, lbl in enumerate(self.seq_labels):      # ← make sure this line is here
            if i < len(seq):
                if seq[i] is None:
                    # REST  → black with a white dash
                    lbl.config(text="–", bg="black", fg="white")
                    lbl.note_midi = None
                else:
                    midi  = seq[i]
                    note  = NOTE_NAMES[midi % 12]
                    color = NOTE_TO_COLOR.get(note, "black")
                    lbl.config(text=self._midi_to_oct(midi), bg=color, fg="black")
                    lbl.note_midi = midi
            else:
                # beyond sequence length → empty
                lbl.config(text="", bg="white", fg="black")
                lbl.note_midi = None

        self._refresh_mode_buttons()
        self.update_counters()

    def on_build(self):
        # Flip mode
        self.state.build_mode_enabled = not self.state.build_mode_enabled

        # Stop sequencer and reset Start button (minimal Korg-level)
        if self.on_stop:
            self.on_stop()
        if hasattr(self.master, 'transport') and hasattr(self.master.transport, 'start_btn'):
            self.master.transport.start_btn.config(relief='raised', bg='SystemButtonFace')

        self._refresh_mode_buttons()
        self.piano._blink_original()

        if self.state.build_mode_enabled:
            self._sync_build_to_state()

        if self.on_state_change:
            self.on_state_change()




    def on_clear(self):
        # ⬅ EARLY EXIT: if build grid is entirely empty, do nothing
        if not any(lbl.note_midi or lbl.rest for lbl in self.build_labels):
            return
        # 1) wipe the Build-mode and Pull-In grids
        for lbl in self.build_labels + self.seq_labels:
            lbl.config(text="", bg='white', fg='black')
            lbl.note_midi = None
            lbl.rest = False
            lbl.disabled = False

        # 2) exit Build mode and reset flags
        self.state.build_mode_enabled = False
        self.state.playback_root = None
        self.state.alt_seq_enabled = False

        # ── Force WRAP mode for refilling full 32-step Pull-In grid ──
        self.state.seq_mode = 0

        self._refresh_mode_buttons()

        # 3) regenerate sequence grid (now guaranteed to be wrap mode)
        self.on_get_default(toggle_mode=False)

        if self.on_state_change:
            self.on_state_change()


    def on_left_single(self, i):
        if not self.state.build_mode_enabled:
            return
        lbl = self.seq_labels[i]
        if lbl.note_midi is not None and self.on_note_play:
            self.on_note_play(lbl.note_midi)
            
        # ── FIX: lift preview by one octave so it matches playback/grid ──
        preview_midi = min(127, lbl.note_midi + 12)   # hard clip at top of range
        self.on_note_play(preview_midi)

    def on_left_double(self, i):
        if not self.state.build_mode_enabled:
            return
        lbl = self.seq_labels[i]
        if lbl.note_midi is not None:
            self.insert_to_right(lbl.note_midi, lbl['bg'])

    def insert_to_right(self, midi, color):
        for lbl in self.build_labels:
            if lbl.note_midi is None and not lbl.rest:
                lbl.config(text=self._midi_to_oct(midi), bg=color)
                lbl.note_midi = midi
                lbl.rest = False
                lbl.disabled = False
                break
        self._sync_build_to_state()

        # Stop playback if we're in build mode
        if self.state.build_mode_enabled and hasattr(self.master, 'event_generate'):
            self.master.event_generate("<<StopSequencer>>")


    def on_right_single(self, i):
        """
        Single‑click toggles mute/disabled **only for note cells**.
        Rests and blank cells ignore single‑click.
        """
        lbl = self.build_labels[i]

        # only notes can be muted
        if lbl.note_midi is None:
            return

        lbl.disabled = not lbl.disabled
        if lbl.disabled:
            lbl.config(bg="gray")
        else:
            note = NOTE_NAMES[lbl.note_midi % 12]
            lbl.config(bg=NOTE_TO_COLOR.get(note, "white"))

        self._sync_build_to_state()

    def on_right_double(self, i):
        lbl = self.build_labels[i]

        if lbl.note_midi is not None or lbl.rest:
            # Clear any note or rest
            lbl.note_midi = None
            lbl.rest = False
            lbl.disabled = False
            lbl.config(text="", bg="white", fg="black")
        else:
            # Insert a rest (– means rest, white background)
            lbl.rest = True
            lbl.disabled = False
            lbl.note_midi = None
            lbl.config(text="–", fg="white", bg="black")

        self._sync_build_to_state()



    def _on_piano_click(self, note):
        if self.state.build_mode_enabled:
            self.state.playback_root = note if self.state.playback_root != note else None
            self.piano.redraw()
            self.master.event_generate("<<RedrawIntervals>>")
            self._transpose_build_sequence() 
            self.piano._blink_original()

        else:
            self.state.selected_notes.clear()
            self.state.selected_notes.add(note)
            self.state.original_root = note

            self.piano.redraw()
            self.master.event_generate("<<RedrawIntervals>>")
            self.on_get_default(toggle_mode=False)

        if self.on_state_change:
            self.on_state_change()


    def set_root(self, root_note):
        """
        Update the big root‐label text and border, choosing
        flats vs sharps per state.use_flats.
        """
        # lookup the enharmonic pair, e.g. "C#/Db"
        enh = ENHARMONIC[ NOTE_NAMES.index(root_note) ]
        # pick the flat or sharp side
        if self.state.use_flats and "/" in enh:
            label = enh.split("/", 1)[1]
        else:
            label = enh.split("/", 1)[0]

        # colour always comes from the canonical NOTE_NAMES entry
        col = NOTE_TO_COLOR.get(root_note, COLORS['text'])

        self.root_label.config(
            text=label,
            fg=col,
            highlightbackground=col,
            highlightcolor=col
        )

    def _toggle_enharmonic(self):
        self.state.use_flats = not self.state.use_flats
        # redraw the big root‐name immediately
        self.set_root(self.state.original_root)
        # then notify everyone else
        if self.on_state_change:
            self.on_state_change()


    def redraw_all(self):
        for lbl in self.seq_labels + self.build_labels:
            lbl.config(text="", bg='white', fg='black')
            lbl.note_midi = None
            lbl.rest = False
            lbl.disabled = False
            self.update_counters()

    def _refresh_mode_buttons(self):
        """
        Update the relief and background color of Alt & Build buttons
        to clearly indicate active (slightly darker) vs inactive.
        """
        inactive_bg = 'SystemButtonFace'  # default button color
        active_bg = 'grey70'              # slightly darker gray for active state

        # Alt Seq button
        if self.state.alt_seq_enabled:
            self.alt_btn.config(relief=tk.SUNKEN, bg=active_bg)
        else:
            self.alt_btn.config(relief=tk.RAISED, bg=inactive_bg)

        # Build button
        if self.state.build_mode_enabled:
            self.build_btn.config(relief=tk.SUNKEN, bg=active_bg)
        else:
            self.build_btn.config(relief=tk.RAISED, bg=inactive_bg)
        
        # Disable Random while in Build mode
        if hasattr(self, 'transport') and hasattr(self.transport, 'random_btn'):
            disabled = tk.DISABLED if self.state.build_mode_enabled else tk.NORMAL
            self.transport.random_btn.config(state=disabled)


            
    def update_counters(self):
        # 1) Build-mode: count the build grid
        if self.state.build_mode_enabled and any(
            lbl.note_midi is not None or lbl.rest
            for lbl in self.build_labels
        ):
            seq = []
            root_diff = 0
            if self.state.playback_root and self.state.original_root:
                try:
                    root_diff = (
                        NOTE_NAMES.index(self.state.playback_root)
                        - NOTE_NAMES.index(self.state.original_root)
                    )
                except ValueError:
                    pass
            for lbl in self.build_labels:
                if getattr(lbl, 'rest', False) or getattr(lbl, 'disabled', False):
                    seq.append(None)
                elif lbl.note_midi is not None:
                    seq.append(lbl.note_midi + root_diff)
        else:
            # 2) Normal/Alt mode: use the base sequence stored in state.last_seq
            seq = self.state.last_seq or []

        # 3) Compute counts
        unique = {n % 12 for n in seq if n is not None}
        total  = sum(1 for n in seq if n is not None)

        # 4) Update the two labels
        self.count_unique_lbl.config(text=str(len(unique)))
        self.count_total_lbl.config(text=str(total))



        
    def _transpose_build_sequence(self):
        if not self.state.playback_root or self.state.playback_root == self.state.original_root:
            return

        seq = []
        for lbl in self.build_labels:
            if getattr(lbl, 'rest', False):
                seq.append(None)
            elif lbl.note_midi is not None:
                interval = (lbl.note_midi % 12 - NOTE_NAMES.index(self.state.original_root)) % 12
                base_oct = lbl.note_midi // 12 - 1  # Yamaha standard
                new_midi = SequenceGenerator(self.state)._midi_from_grid(
                    self.state.playback_root, interval, base_oct
                )
                seq.append(new_midi)

        self.state.last_seq = seq
        if hasattr(self.master, 'transport') and hasattr(self.master.transport, 'export_panel'):
            self.master.transport.export_panel.update_buttons()