# chain_runner.py — daemon-friendly, minimal playlist runner
import threading, time, math
from sequence_engine import SequenceGenerator

INF = float("inf")

def _parse_loops(v):
    # per-slot loop count: 1, 2, ..., or None/'x' for infinite
    if v is None: return None
    if isinstance(v, str) and v.strip().lower() in ("x","none",""): return None
    try:
        n = int(v)
        return max(1, n)
    except Exception:
        return 1

# replace the old parser
def _parse_global_loops(s):
    if s is None:
        return 1           # default = one pass
    s = str(s).strip().lower()
    if s in ("",):         # empty = one pass
        return 1
    if s in ("x", "inf", "∞", "none"):
        return INF
    try:
        return max(1, int(s))
    except Exception:
        return 1


class ChainRunner:
    def __init__(self, state, midi_engine, on_tick, on_done, global_loops=""):
        self.state = state
        self.m = midi_engine
        self.on_tick = on_tick          # (slot_idx, current_loop, total_loops, is_active)
        self.on_done = on_done          # callback when global loops complete
        self.global_loops = _parse_global_loops(global_loops)
        self.global_loop_counter = 0
        self._cur_idx = None
        self._cur_total = None
        self.active_slots = []          # list of dicts: {idx, snap, loops}
        self._stop = threading.Event()
        self._thr = None
        self.running = False

        self.rebuild_active_slots()

    # PUBLIC: reflect GUI changes (mute/solo/order/loops)
    def rebuild_active_slots(self):
        snaps = getattr(self.state, "chain_arps_list", []) or []
        # SOLO logic: if any solo=True, only play those; otherwise play non-muted, non-hidden
        solo_idxs = [i for i,s in enumerate(snaps)
                     if s and not s.get("hidden") and s.get("solo")]
        picks = []
        for i, s in enumerate(snaps):
            if not s or s.get("hidden"): 
                continue
            if solo_idxs and not s.get("solo"):
                continue
            if s.get("muted"):
                continue
            picks.append(dict(idx=i, snap=s, loops=_parse_loops(s.get("loop_count", 1))))
        self.active_slots = picks

    def start(self):
        if self.running: return
        self._stop.clear()
        self.running = True
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self):
        if self._stop.is_set() and not (self._thr and self._thr.is_alive()):
            return
        self._stop.set()
        self.running = False

        # tell UI to unhighlight current row
        if self.on_tick and self._cur_idx is not None:
            try:
                self.on_tick(self._cur_idx, 0, self._cur_total, False)
            except Exception:
                pass
        self._cur_idx = None
        self._cur_total = None

        # ✅ ensure the thread actually dies before we return
        thr = self._thr
        self._thr = None
        if thr and thr.is_alive():
            try:
                thr.join(timeout=0.25)
            except Exception:
                pass
            
    def _daemon_chain_active(self):
        # MidiEngine exposes _chain_active; treat truthy as “daemon owns playback”
        return bool(getattr(self.m, "_chain_active", False))

    def _loop_seconds_for_snapshot(self, snap):
        """
        Duration of one full pass through the slot’s baked sequence under current transport.
        Uses daemon transport (tempo/subdiv) so UI tickers stay in sync while we stay hands-off.
        """
        seq = snap.get("sequence") or []
        steps = len(seq)
        if steps <= 0:
            return 0.05
        tempo = float(self.m.get_tempo())
        subdiv = max(1, int(self.m.get_subdivision()))
        step_sec = (60.0 / max(1e-3, tempo)) * (4.0 / float(subdiv))
        return steps * step_sec



    # ---- internals ---------------------------------------------------

    def _apply_snapshot_to_state(self, snap):
        if 'root' in snap and snap['root'] is not None:
            self.state.original_root = snap['root']
        if 'scale' in snap and snap['scale'] is not None:
            self.state.scale = snap['scale']
        if 'scale_notes' in snap:
            self.state.scale_notes = set(snap.get('scale_notes') or [])

        # sets & dict[iv]->set(octs)
        if 'selected_intervals' in snap:
            self.state.selected_intervals = set(snap.get('selected_intervals') or [])
        if 'extension_octaves' in snap:
            raw = snap.get('extension_octaves') or {}
            self.state.extension_octaves = {int(k): set(v or []) for k, v in raw.items()}

        if 'direction_mode' in snap and snap['direction_mode'] is not None:
            self.state.direction_mode = snap['direction_mode']
        if 'gate_pct' in snap and snap['gate_pct'] is not None:
            g = float(snap['gate_pct'])
            self.state.gate = g
            self.state.gate_pct = g
        if 'diatonic_mode' in snap:
            self.state.diatonic_mode = bool(snap['diatonic_mode'])
            
        if 'subdivision' in snap and snap['subdivision'] is not None:
            self.state.subdivision = int(snap['subdivision'])
        if 'bpm' in snap and snap['bpm'] is not None:
            self.state.tempo = float(snap['bpm'])


        # Recompute the audible pattern for this snapshot
        self.state.last_seq = [n if (n is None) else int(n) for n in (snap.get("sequence") or [])]

        # Push everything to the daemon right now
        self.m._push_all(immediate=True)

    def _loop_seconds(self):
        # duration of one “pattern loop” = steps * step_duration
        steps = len(getattr(self.state, "last_seq", []) or [])
        if steps <= 0: 
            return 0.05  # nothing to play, advance quickly
        tempo = self.m.get_tempo()
        subdiv = max(1, int(self.m.get_subdivision()))
        step_sec = (60.0 / max(1e-3, tempo)) * (4.0 / float(subdiv))
        return steps * step_sec

    def _run(self):
        if not self.active_slots:
            self.running = False
            return

        while not self._stop.is_set():
            # One pass through all active slots
            for slot in list(self.active_slots):  # snapshot, in case GUI rebuilds
                if self._stop.is_set():
                    break

                idx   = slot['idx']
                snap  = slot['snap']
                loops = slot['loops']  # None => infinite

                current = 0
                while not self._stop.is_set() and (loops is None or current < loops):
                    # Only push state/sequence when NOT using the daemon's chain
                    if not self._daemon_chain_active():
                        self._apply_snapshot_to_state(snap)

                    current += 1
                    total_disp = 'X' if loops is None else loops
                    if self.on_tick:
                        self.on_tick(idx, current, total_disp, True)
                    self._cur_idx = idx
                    self._cur_total = total_disp

                    # Sleep exactly one loop; wake often so stop() is responsive
                    remain = (
                        self._loop_seconds_for_snapshot(snap)
                        if self._daemon_chain_active()
                        else self._loop_seconds()
                    )
                    t0 = time.time()
                    while remain > 0 and not self._stop.is_set():
                        time.sleep(min(0.02, remain))
                        # recompute remaining with current tempo/subdiv
                        if self._daemon_chain_active():
                            remain = self._loop_seconds_for_snapshot(snap) - (time.time() - t0)
                        else:
                            remain = self._loop_seconds() - (time.time() - t0)

            if self._stop.is_set():
                break

            # Global loop book-keeping
            if self.global_loops is INF:
                continue
            self.global_loop_counter += 1
            if self.global_loop_counter >= self.global_loops:
                # Clean finish: counters show 0 and LINK remains on
                self.running = False
                if self.on_tick and self._cur_idx is not None:
                    try:
                        self.on_tick(self._cur_idx, 0, self._cur_total, False)
                    except Exception:
                        pass
                if self.on_done:
                    self.on_done()
                break

        self.running = False

