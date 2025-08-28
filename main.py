#main.py

import tkinter as tk
from PIL import Image, ImageTk
import random
import sys
import json, socket, threading, os
from utils import NOTE_NAMES, KeyMapper
from config import COLORS, NOTE_TO_COLOR, MIDI_PORT_NAME
from state import AppState
from theory import SCALES, NOTE_NAMES
from grid_panel import IntervalGridPanel
from sequence_panel import SequencePanel
from transport_panel import TransportPanel
from midi_engine import MidiEngine
from sequence_engine import SequenceGenerator
from utils import resource_path
from chain_runner import ChainRunner
from chain_arps import ChainArpsWindow
from rt_daemon import GordRTDaemon
import atexit 

# ── Main ──────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.title("GORD")
    root.configure(bg=COLORS['bg'])

    IAC_DEST   = "gord out"
    IAC_SRC_IN = "gord in"


    os.environ["GORD_MIDI_DEST"] = IAC_DEST
    os.environ["GORD_MIDI_SRC"]  = IAC_SRC_IN


    daemon = GordRTDaemon(dest=IAC_DEST)

    try:
        daemon.stop()
        os.remove("/tmp/gord_rt.sock")
    except Exception:
        pass

    daemon.ensure_running()
    atexit.register(daemon.stop)

        
    # Size & DPI on mac (Retina can make widgets huge)
    try:
        if sys.platform == "darwin":
            # Halve Tk’s DPI scaling on Retina so buttons aren’t gigantic
            root.tk.call("tk", "scaling", 0.9)   # try 0.9 or 0.8 if you want smaller
            root.geometry("880x660")            # roomier default on mac
            root.resizable(True, True)           # allow resize while we tune
        else:
            root.geometry("980x656")
            root.resizable(False, False)
    except Exception:
        pass

        
    # ── App icon (Windows .ico; mac uses PNG via iconphoto) ─────────
    ico_path = resource_path("assets/gord_icon.ico")
    png_path = resource_path("assets/gord_icon.png")

    try:
        # Windows: loads .ico in title bar/taskbar
        # (no "default=" arg; mac will raise here and fall through)
        root.iconbitmap(ico_path)
    except Exception:
        # macOS dev run: use PNG instead
        try:
            icon_png = tk.PhotoImage(file=png_path)
            root.iconphoto(True, icon_png)
        except Exception:
            pass  # no icon is fine in dev


    # ── Global state ────────────────────────────────────────────────
    state = AppState()
    engine = MidiEngine(state)
    engine.panic()
    state.last_seq = SequenceGenerator(state).get_sequence_list()  # initial empty list
    state._prev_root = state.original_root 

    # ── Helper: rebuild sequence from state ────────────────────────
    def regenerate_sequence():
        state.last_seq = SequenceGenerator(state).get_sequence_list()

    def snap_to_key(pc: int, key_pcs: list[int]) -> int:
        """If pc isn’t in key, step up until it is (diatonic snap-up)."""
        while pc not in key_pcs:
            pc = (pc + 1) % 12
        return pc
        



    # ────────────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────────────────
    def on_change():
        """
        Unified updater.

        Behavior:
        - Always build the base sequence at the CURRENT root.
        - If Diatonic+Stay-In-Key are ON, snap each note UP into the ANCHOR key.
        - Pull-In grid root label stays on the CURRENT root (so the visuals follow your keybed).
        """

        # 1) Base sequence (at current root)
        if not state.build_mode_enabled:
            base_seq = SequenceGenerator(state).get_sequence_list()
        else:
            base_seq = state.last_seq[:]  # respect Build mode

        # 2) Compute allowed pitch-classes
        state.scale_notes = set()
        if state.diatonic_mode and getattr(state, "scale", None):
            from utils import calc_scale_notes, snap_to_scale
            # Anchor key tonic stays fixed while Stay-In-Key is ON
            anchor_tonic = (getattr(state, "key_anchor", None) or state.original_root) if getattr(state, "stay_in_key", False) else state.original_root
            state.scale_notes = calc_scale_notes(anchor_tonic, state.scale)

            # 3) If we are staying in key, snap EVERY note (prefer upward)
            if getattr(state, "stay_in_key", False):
                snapped = []
                for n in base_seq:
                    if n is None:
                        snapped.append(None)
                    else:
                        snapped.append(snap_to_scale(n, state.scale_notes))  # tries +1, -1, +2, -2...
                state.last_seq = snapped
            else:
                # Plain diatonic filter/snap when not staying in key
                state.last_seq = [snap_to_scale(n, state.scale_notes) if n is not None else None for n in base_seq]
        else:
            # No diatonic behavior
            state.last_seq = base_seq

        # Keep selection to the current root (the grid header & pull-in root should follow the keybed)
        state.selected_notes = {state.original_root}

        # ---------- refresh GUI ----------
        piano.redraw()
        grid.update_grid()
        grid._refresh_overlays()
        grid.update_notes_row()
        seq.update_counters()

        # IMPORTANT: pull-in grid should display relative to CURRENT root
        seq.set_root(state.original_root)

        transport.update_export_buttons()




    def on_note_play(midi):
        port = getattr(engine, "port", None)
        make_on  = getattr(engine, "make_note_on", None)
        make_off = getattr(engine, "make_note_off", None)
        if port and make_on and make_off:
            port.send(make_on(midi))
            root.after(200, lambda: port.send(make_off(midi)))


    def on_start():
        if state.chain_mode_enabled:
            if state.chain_runner is None:
                raw = state.chain_arps_window.global_loops_var.get().strip().lower()
                state.chain_runner = ChainRunner(
                    state, engine,
                    state.chain_arps_window._update_ticker_for_row,
                    state.chain_arps_window._on_chain_complete,
                    global_loops=raw
                )
            if not state.chain_runner.running:
                state.chain_runner.start()

        engine.start()
        state.is_running = True



    def on_stop():
        if state.chain_runner:
            state.chain_runner.stop()
        engine.stop()
        state.is_running = False


    # ------------------------------------------------------------------
    def on_random():
        # --- normalize collections for Random ---
        if not isinstance(getattr(state, "selected_intervals", None), set):
            state.selected_intervals = set()
        if not isinstance(getattr(state, "extension_octaves", None), dict):
            state.extension_octaves = {}
        if not isinstance(getattr(state, "muted_intervals", None), set):
            state.muted_intervals = set()

        # Skip if Build-mode is running
        if state.build_mode_enabled:
            return
    
        # ── 1) randomise root ───────────────────────────────────────
        new_root = random.choice(NOTE_NAMES)
        state.selected_notes   = {new_root}
        state.original_root    = new_root
        state.playback_root    = None   # reset step-preview root

        # ── 2) randomise intervals & octaves ─────────────────────────
        state.selected_intervals.clear()
        state.extension_octaves.clear()
        state.muted_intervals.clear()

        num_ivs = random.randint(4, 7)                  # pick 4–7 UNIQUE intervals
        for iv in random.sample(range(0, 13), k=num_ivs):  # 0..12 inclusive
            k_oct = random.randint(1, 3)                # 1–3 octaves per interval
            octs  = set(random.sample(range(0, 9), k=k_oct))  # 0..8
            state.selected_intervals.add(iv)
            state.extension_octaves[iv] = octs

        # ── 3) refresh Stay-In-Key snapshot if that mode is active ──
        if state.stay_in_key and state.diatonic_mode:
            from utils import KeyMapper
            state.key_mapper = KeyMapper.from_grid(state)
        else:
            state.key_mapper = None

        # ── 4) redraw UI & regenerate sequence ──────────────────────
        # (rebuild last_seq and refresh the UI)
        seq.redraw_all()     # clears pull-in grids; user can Pull-In again
        on_change()



    # ------------------------------------------------------------------
    def on_clear():
        # wipe out note choices & sequence data
        state.selected_intervals.clear()
        state.extension_octaves.clear()
        state.muted_intervals.clear()
        state.last_seq.clear()

        # exit any Build-mode preview
        state.build_mode_enabled = False

        # drop the Stay-In-Key snapshot (will rebuild on next click)
        state.key_mapper = None

        seq.redraw_all()        # clear the grids visually
        on_change()


    def handle_note_click(note):
        if state.build_mode_enabled:
            state.playback_root = note if state.playback_root != note else None
            piano.redraw()
        else:
            state.selected_notes.clear()
            state.selected_notes.add(note)
            state.original_root = note
            on_change()

    # ── Grid column weights ────────────────────────────────────────
    root.columnconfigure(0, weight=1)   # interval grid
    root.columnconfigure(1, weight=1)   # transport / export
    root.columnconfigure(2, weight=1)   # piano + sequence

    # ── Middle: Transport + Export stack ───────────────────────────
    transport = TransportPanel(
        root, state,
        icon_path=resource_path("assets/gord_icon.png"),
        on_start=on_start,
        on_stop=on_stop,
        on_random=on_random,
        on_clear=on_clear,
        on_direction_change=on_change
    )
    transport.grid(row=0, column=1, sticky='n', padx=(0, 0), pady=(42, 0))
    root.transport = transport 
    


    


    # ── MIDI Engine wiring — daemon-driven timing ───────────────────
    state.midi_engine = engine
    state.chain_runner = None
    engine.update_slave(bool(transport.get_slave_mode()))



    # ── Left: Interval / Octave grid ───────────────────────────────
    grid = IntervalGridPanel(root, state, engine, on_change=on_change)
    root.bind("<<RedrawIntervals>>", lambda e: grid._refresh_overlays())
    grid.grid(row=0, column=0, sticky='n', padx=(0, 0), pady=(20, 0))

    # ── Right: Sequence / Piano panel ──────────────────────────────
    seq = SequencePanel(
        root,
        state,
        on_note_play=on_note_play,
        on_state_change=on_change,
        on_stop=on_stop
    )
    seq.grid(row=0, column=2, sticky='n', padx=(0, 12), pady=(42, 0))
    piano = seq.piano
    piano.root_label.pack_forget()  # hide duplicate root note beside piano

    # Wire transport to sequence panel
    seq.transport = transport
    

    def _toggle_space(event=None):
        playing = bool(getattr(state, "is_running", False))

        if playing:
            on_stop()
            transport.start_btn.config(relief=tk.RAISED, bg='SystemButtonFace')
        else:
            on_start()
            transport.start_btn.config(relief=tk.SUNKEN, bg='grey70')




    # ── Mainloop ───────────────────────────────────────────────────
    root.mainloop()


# ── Entry point ────────────────────────────────────────────────────
if __name__ == '__main__':
    main()

