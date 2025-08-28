# sequence_engine.py

from config import NOTE_NAMES, MAX_OCTAVE
from theory import SCALES
from utils import interval_to_degree, snap_to_scale

class SequenceGenerator:
    """
    Generates default and alternate note sequences based on AppState:
    - selected_notes (root)
    - selected_intervals
    - extension_octaves
    - muted_intervals
    - alt_seq_enabled
    - direction_mode, include_turnaround
    """
    def __init__(self, state):
        self.state = state



    def get_default_sequence(self):
        st = self.state

        # ── 1) Diatonic rebuild directly from grid ────────────────────
        if st.diatonic_mode and st.scale:
            if not st.selected_notes:
                return []

            root      = st.playback_root or next(iter(st.selected_notes))
            scale_ivs = SCALES[st.scale]["intervals"]        # e.g. [0,2,4,7,9]
            seq       = []

            for iv in sorted(st.selected_intervals):
                if iv in st.muted_intervals:
                    continue

                deg_idx = interval_to_degree(iv, st.scale)   # None if chromatic
                octvs   = sorted(st.extension_octaves.get(iv, []))

                for o in octvs:
                    if deg_idx is not None:
                        # Pure diatonic: map the degree index back to an interval
                        mapped_iv = scale_ivs[deg_idx]
                        note = self._midi_from_grid(root, mapped_iv, o)
                    else:
                        # Chromatic: use raw interval, then snap to nearest scale
                        note = self._midi_from_grid(root, iv, o)
                        note = snap_to_scale(note, st.scale_notes)

                    seq.append(note)
            return seq

        # ── 2) Original chromatic logic (diatonic mode off) ───────────
        if not st.selected_notes:
            return []

        root = st.playback_root or next(iter(st.selected_notes))
        seq  = []
        for iv in sorted(st.selected_intervals):
            if iv in st.muted_intervals:
                continue
            for o in sorted(st.extension_octaves.get(iv, [])):
                seq.append(self._midi_from_grid(root, iv, o))
        return seq
    # ────────────────────────────────────────────────────────────
    # Alt-Seq helper  (keep this inside SequenceGenerator)
    # ────────────────────────────────────────────────────────────
    def _build_alt_cycle(self):
        """
        ALT sequence = weave across per-interval octave lists (wrap-around).
        This yields a different count than default when lists are uneven.
        Mirrors the old SequencePanel._weave_alt() semantics, but keeps
        diatonic handling consistent with get_default_sequence().
        """
        st = self.state
        if not st.selected_notes:
            return []

        root = st.playback_root or next(iter(st.selected_notes))
        use_diatonic = bool(getattr(st, "diatonic_mode", False) and st.scale)
        scale_ivs = SCALES[st.scale]["intervals"] if use_diatonic else None

        lists = []
        for iv in sorted(st.selected_intervals):
            if iv in st.muted_intervals:
                continue
            octs = sorted(st.extension_octaves.get(iv, []))
            if not octs:
                continue

            if use_diatonic:
                deg_idx = interval_to_degree(iv, st.scale)  # None if chromatic vs scale
                seq = []
                for o in octs:
                    if deg_idx is not None:
                        mapped_iv = scale_ivs[deg_idx]
                        note = self._midi_from_grid(root, mapped_iv, o)
                    else:
                        note = self._midi_from_grid(root, iv, o)
                        note = snap_to_scale(note, st.scale_notes)
                    seq.append(note)
            else:
                seq = [self._midi_from_grid(root, iv, o) for o in octs]

            if seq:
                lists.append(seq)

        if not lists:
            return []

        # weave with wrap-around so shorter lists repeat
        max_len = max(len(l) for l in lists)
        woven = []
        for i in range(max_len):
            for l in lists:
                woven.append(l[i % len(l)])
        return woven



    def get_sequence_list(self):
        """
        Return the final play list, applying:
          • default vs alt mode
          • direction / ping-pong options
        """
        # 1) base sequence
        if self.state.alt_seq_enabled:
            seq = self._build_alt_cycle()          # new alt logic

        else:
            seq = self.get_default_sequence()      # existing default builder

        # 2) apply direction modes (unchanged)
        if self.state.direction_mode == 1:                 # reverse
            seq = list(reversed(seq))
        elif self.state.direction_mode in (2, 3):          # ping-pong
            rev = list(reversed(seq))
            if self.state.direction_mode == 2:             # forward then backward
                seq = seq + rev
                if not self.state.include_turnaround:
                    seq = seq[:-1]
            else:                                          # backward then forward
                seq = rev + seq
                if not self.state.include_turnaround:
                    seq = seq[1:]

        return seq
    
    def _midi_from_grid(self, root, interval, octave):
        root_index = NOTE_NAMES.index(root)
        semitone = (root_index + interval) % 12
        midi = 12 * (octave + 1) + semitone
        return midi


