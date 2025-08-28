# state.py
from collections import defaultdict
import json


class AppState:
    def __init__(self):
        # ── Root & Playback Notes ──
        self.selected_notes = {"C"}
        self.original_root = "C"
        self.playback_root = None
        # ── How to display enharmonic names: False=sharps (default), True=flats
        self.use_flats = False
        self.stay_in_key   = False
        self.key_mapper = None

        # ── Interval & Octave Config ──
        self.selected_intervals = set()
        self.extension_octaves = defaultdict(set)
        self.muted_intervals = set()
        self.last_selection_label = ""  # tooltip text for current scale/chord

        # ── MIDI OUTPUT MODES ──
        self.octave_channel_map = {}          # octave index (0–8) → MIDI channel (1–16)
        self.note_channel_overrides = {}      # MIDI note (0–127) → MIDI channel
        self.interval_channel_map = {}        # interval index (0=root, 1=b2...) → MIDI channel
        
        self.chain_emit_lock = False  # suppress _emit_chain() during critical sections

        self.key_anchor = None        # holds the tonic when Stay-In-Key is ON
        self.locked_scale_pcs = None   # set of pitch-classes that stay framed


        # ── Sequencer Modes ──
        self.alt_seq_enabled = False
        self.direction_mode = 0
        self.include_turnaround = True
        
        # ── MIDI slave mode ──
        self.slave_mode = False  # <— REQUIRED
        

        # ── NEW  ▸ Global Scale Filter ──
        # When True, every outgoing note is snapped to the current scale
        self.diatonic_mode = False            # ← core flag for new feature
        self.scale_notes = set()              # set( pitch-classes ) for fast filtering
        self.scale = None
        
        # ── Chain Arps State ──
        self.chain_arps_list = []  # list of ArpSnapshot dicts or None per row
        self.chain_mode_enabled = False
        self.chain_runner = None   # ← add this
        self.engine_running = False
        self.chain_global_loops = "1"



        # ── Build & Transport State ──
        self.build_mode_enabled = False
        self.running = False
        self.last_seq = []
        self.bpm = 120
        self.gate_pct = 80
        self.subdivision = 4
        self.transport_subdivision = 16

        # ── GUI Paging / Display ──
        self.seq_mode = 0           # toggles Pull-In pages
        self.name_mode = 0          # 0=full names, 1=deduped
        self.midi_shown = False
        self.step_index = -1        # tick index counter

    # ────────────────────────────────────────────────────────────────
    # Lightweight (de)serialisation helpers
    # ────────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Return a JSON-friendly snapshot of the state (sets → lists)."""
        data = self.__dict__.copy()
        # convert non-serialisable types
        data['selected_notes']    = list(self.selected_notes)
        data['selected_intervals'] = list(self.selected_intervals)
        data['muted_intervals']   = list(self.muted_intervals)
        data['scale_notes']       = list(self.scale_notes)
        return data

    def from_dict(self, data: dict):
        """Restore state from dict (safe defaults for older saves)."""
        self.__dict__.update(data)
        # convert lists back to sets / defaultdict
        self.selected_notes       = set(data.get('selected_notes', {"C"}))
        self.selected_intervals   = set(data.get('selected_intervals', []))
        self.muted_intervals      = set(data.get('muted_intervals', []))
        self.scale_notes          = set(data.get('scale_notes', []))
        # diatonic_mode defaults gracefully if not present
        self.diatonic_mode        = data.get('diatonic_mode', False)
