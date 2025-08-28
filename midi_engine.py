# midi_engine.py — daemon-driven transport (KORG-level minimal, anti-trill + empty-start fix)
import threading, time, json, socket
from utils import snap_to_scale

# ----------------------------
#  UDP client for Swift daemon
# ----------------------------
class GordRTClient:
    def __init__(self, path="/tmp/gord_rt.sock"):
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        # debug signatures to avoid spam
        self._dbg_last_seq = None
        self._dbg_last_chain = None
        
        

    def _send(self, obj: dict):
        # --- minimal one-line TX probe (only on content change) ---
        try:
            cmd = obj.get("cmd")
            if cmd == "seq":
                real = tuple(n for n in obj.get("notes", []) if n != -1)
                if real and real != self._dbg_last_seq:
                    print(f"[GORD→DAEMON] SEQ n={len(real)} head={list(real)[:8]}")
                    self._dbg_last_seq = real
            elif cmd == "chain":
                slots = obj.get("slots", [])
                sig = tuple(tuple(n for n in s.get("notes", []) if n != -1) for s in slots)
                if sig and sig != self._dbg_last_chain:
                    lens = [len(s) for s in sig]
                    print(f"[GORD→DAEMON] CHAIN slots={len(sig)} lens={lens} index={obj.get('index',0)}")
                    self._dbg_last_chain = sig
            elif cmd in ("start", "stop"):
                print(f"[GORD→DAEMON] {cmd.upper()}")
        except Exception:
            pass
        # -----------------------------------------------------------
        try:
            self.sock.sendto(json.dumps(obj).encode("utf-8"), self.path)
        except OSError:
            pass

    def set_params(self, *, tempo=None, subdivision=None, gate=None,
                   channel=None, transpose=None, slave_mode=None,
                   immediate=False):
        msg = {"cmd": "set"}
        if tempo is not None:        msg["tempo"]       = float(tempo)
        if subdivision is not None:  msg["subdivision"] = int(subdivision)
        if gate is not None:         msg["gate"]        = float(gate)     # 1..99 %
        if channel is not None:      msg["channel"]     = int(channel)
        if transpose is not None:    msg["transpose"]   = int(transpose)
        if slave_mode is not None:   msg["slave_mode"]  = bool(slave_mode)
        if immediate:                msg["immediate"]   = True
        self._send(msg)
        
    def set_sequence(self, notes):
        def norm(n):
            # ⬅ allow true rests through
            try:
                nn = int(n)
            except Exception:
                return -1
            return -1 if nn < 0 else max(0, min(127, nn))

        payload = {
            "cmd": "seq",
            "notes": [norm(n) for n in (notes or [])]
        }
        self._send(payload)


    def set_chain(self, slots, index=0):
        def _loops(v):
            if v is None: return -1
            if isinstance(v, str) and v.strip().lower() in ("x","none",""): return -1
            try: return max(1, int(v))
            except: return 1
        payload = {"cmd":"chain","slots":[{"notes":[-1 if n is None else int(n) for n in s.get("notes",[])],
                                           "loops":_loops(s.get("loops",1))} for s in slots],
                   "index": int(index)}
        lens  = [len(s.get("notes", [])) for s in slots]
        loops = [_loops(s.get("loops", 1)) for s in slots]
        print(f"[GORD→DAEMON] CHAIN slots={len(slots)} lens={lens} loops={loops} index={index}")
        self._send(payload)

    def start(self): self._send({"cmd": "start"})
    def stop(self):  self._send({"cmd": "stop"})
    def panic(self): self._send({"cmd": "panic"})


# ----------------------------
#            Engine
# ----------------------------
class MidiEngine:
    """
    - Mirrors params/seq to the Swift daemon (debounced)
    - Idempotent Start/Stop (no “burst”/”trill” leftovers)
    - Slave mode respected
    - Chain arming support
    - Auto-rearm if Start happened with an empty sequence
    """
    def __init__(self, state, sock="/tmp/gord_rt.sock"):
        self.state = state
        self._rt = GordRTClient(sock)

        self._chain_active = False
        self._last_key = None
        self._armed_restart = False   # if Start when seq was empty
        self._prev_t = None
        self._prev_s = None
        self._prev_gate = None
        self._prev_params_sig = None   # (tempo, subdiv, gate, ch, tr, slave)
        self._prev_seq_sig    = None   # tuple(seq) or "CHAIN"
        self._last_chain = None 
        
        # known-silent baseline
        try:
            self._rt.set_sequence([-1])
        except Exception:
            pass

        self._thr = threading.Thread(target=self._mirror_loop, daemon=True)
        self._thr.start()

    # ---------- tiny getters ----------
    def set_sequence(self, notes):
        """
        Push a new step list to the daemon immediately (used for the ACTIVE slot while linked).
        Notes may include None; we'll map to -1 for rests.
        """    
        seq = [int(n) if n is not None else -1 for n in (notes or [])]
        try:
            self._rt.set_sequence(seq)
            self._prev_seq_sig = tuple(seq)
        except Exception:
            pass
        
    def _map_out_note(self, n):
        if n is None or n == -1:
            return -1
        n_out = int(n) + self.get_transpose() + 12
        if bool(getattr(self.state, "diatonic_mode", False)) and (getattr(self.state, "scale_notes", None) or []):
            n_out = snap_to_scale(n_out, getattr(self.state, "scale_notes", []))
        return max(0, min(127, n_out))


    def get_subdivision(self) -> int:
        return int(getattr(self.state, "subdivision", 16))

    def get_tempo(self) -> float:
        # Prefer bpm; fall back to legacy 'tempo' if present.
        return float(getattr(self.state, "bpm", getattr(self.state, "tempo", 120.0)))


    def get_channel(self) -> int:
        return int(getattr(self.state, "default_channel", 1))

    def get_transpose(self) -> int:
        return int(getattr(self.state, "transpose", 0))

    def is_slave(self) -> bool:
        return bool(getattr(self.state, "slave_mode", False))

    def get_gate(self) -> float:
        raw = getattr(self.state, "gate", getattr(self.state, "gate_pct", 45.0))
        try:
            g = float(raw)
        except Exception:
            g = 45.0
        if g > 1.5:
            g = g / 100.0
        return max(0.01, min(0.99, g))

    def _gate_pct(self) -> float:
        raw = getattr(self.state, "gate", getattr(self.state, "gate_pct", 45.0))
        try:
            g = float(raw)
        except Exception:
            g = 45.0
        if g <= 1.5:
            g *= 100.0
        return max(1.0, min(99.0, g))

    # ---------- public transport ----------
    def panic(self):
        try:
            self._rt.panic()
        finally:
            self._flush_silence()

    def start(self):
        """
        Start transport cleanly.
        - Chain mode: don't flush/overwrite daemon notes; just push params and (if non-slave) start.
        - Non-chain: stop -> flush -> set params -> set sequence -> start.
        """
        # Arm restart only when we're driving a base sequence (not chain)
        if self._chain_active:
            self._armed_restart = False
            seq_list = None
        else:
            seq_list = self._build_seq()
            is_empty = (len(seq_list) == 0) or all(n == -1 for n in seq_list)
            self._armed_restart = is_empty

        # Stop first to drain any scheduler state
        self._rt.stop()

        # Only hard-silence when NOT in chain mode
        if not self._chain_active:
            self._flush_silence()

        # Push params immediately so scheduler picks them up before first tick
        self._rt.set_params(
            tempo=self.get_tempo(),
            subdivision=self.get_subdivision(),
            gate=self._gate_pct(),
            channel=self.get_channel(),
            transpose=self.get_transpose(),
            slave_mode=self.is_slave(),
            immediate=True,
        )

        # In chain mode the daemon already owns notes; do NOT send a base sequence
        if not self._chain_active:
            self._rt.set_sequence(seq_list)
            self._prev_seq_sig = tuple(seq_list)
        else:
            # 🔒 ensure chain is armed before we hit START
            if self._last_chain:
                mapped, idx = self._last_chain
                try:
                    self._rt.set_chain(mapped, int(idx))
                except Exception:
                    pass


        # Host clock starts us in slave; only start when we’re master
        if not self.is_slave():
            time.sleep(0.01)  # tiny barrier so params latch
            self._rt.start()



    def stop(self):
        # Stop the daemon transport only
        self._rt.stop()

        # Stop Python ChainRunner ticker
        cr = getattr(self.state, "chain_runner", None)
        if cr:
            try: cr.stop()
            except Exception: pass

        # DO NOT tear down chain or push silence here.
        # Keep LINK armed so next Start resumes the same chain.
        self._last_key = None
        self._armed_restart = False
        # self._chain_active stays as-is (True if LINKed)


    def update_slave(self, flag: bool):
        self.state.slave_mode = bool(flag)
        # params only; no chain re-arm
        self._rt.set_params(slave_mode=self.state.slave_mode, immediate=True)
        # keep audio clean
        if not self._chain_active:
            self._flush_silence()
        self._push_all(immediate=True)



    # ---------- chain ----------
    def play_chain(self, slots, index=0):
        # if transport already running and we are master, resume after re-arm
        should_restart = bool(getattr(self.state, "is_running", False)) and not self.is_slave()

        # HARD barrier: stop daemon and clear any scheduled base SEQ ticks
        try:
            self._rt.stop()
        except Exception:
            pass

        self._chain_active = True

        # Clear base SEQ lane so only CHAIN can sound
        try:
            self._rt.set_sequence([-1])
        except Exception:
            pass
        self._prev_seq_sig = tuple([-1])  # prevent mirror loop from re-pushing SEQ

        # Push current params (tempo/subdiv/gate/ch/tr/slave); when _chain_active=True this won't push SEQ
        self._push_all(immediate=True)

        # Map & arm chain slots
        mapped = []
        for s in (slots or []):
            mapped.append({
                "notes": [self._map_out_note(n) for n in s.get("notes", [])],
                "loops": s.get("loops", 1),
            })
        self._last_chain = (mapped, int(index))

        if mapped:
            self._rt.set_chain(mapped, int(index))
            # if transport is running and we are master, start immediately
            if should_restart:
                try:
                    time.sleep(0.005)  # small latch so params/chain settle
                    self._rt.start()
                except Exception:
                    pass
        else:
            # no slots -> leave SEQ cleared; nothing to start
            pass




    def stop_chain(self):
        self._chain_active = False
        try:
            self._rt.set_chain([], 0)
        finally:
            # Force silence instead of reverting to base sequence
            self._rt.set_sequence([-1])
            self._prev_seq_sig = tuple([-1])  # block mirror loop from re-pushing base seq


    # ---------- internals ----------
    def _flush_silence(self):
        # don't overwrite daemon notes while a chain is active
        if self._chain_active:
            return
        try:
            self._rt.set_sequence([-1])
        except Exception:
            pass

    def _build_seq(self):
        seq = getattr(self.state, "last_seq", None) or []
        dia = bool(getattr(self.state, "diatonic_mode", False))
        scale = getattr(self.state, "scale_notes", None) or []
        tr = int(getattr(self.state, "transpose", 0))
        out = []
        for n in seq:
            if n is None:
                out.append(-1)
                continue
            n_out = int(n) + tr + 12
            if dia and scale:
                n_out = snap_to_scale(n_out, scale)
            n_out = max(0, min(127, n_out))
            out.append(n_out)
        return out

    def _push_all(self, immediate=True):
        t  = self.get_tempo()
        s  = self.get_subdivision()
        gP = self._gate_pct()
        ch = self.get_channel()
        tr = self.get_transpose()
        sl = self.is_slave()

        self._rt.set_params(
            tempo=t, subdivision=s, gate=gP,
            channel=ch, transpose=tr, slave_mode=sl,
            immediate=bool(immediate)
        )
        if not self._chain_active:
            self._rt.set_sequence(self._build_seq())

    def _quiesce_param_change(self, new_seq):
        """
        Apply tempo/subdiv changes without tails/trills.
        - If stopped: just push.
        - If slave: drain (only if not in chain), push params/seq (host clock advances).
        - If master: stop -> (drain only if not in chain) -> push -> start.
        """
        running = bool(getattr(self.state, "is_running", False))
        if not running:
            self._push_all(immediate=True)
            return

        if self.is_slave():
            if not self._chain_active:
                self._flush_silence()
            self._push_all(immediate=True)
        else:
            self._rt.stop()
            if not self._chain_active:
                self._flush_silence()
            self._push_all(immediate=True)
            self._rt.start()



    def _mirror_loop(self):
        while True:
            try:
                # read current state
                t   = round(self.get_tempo(), 4)
                s   = int(self.get_subdivision())
                gP  = round(self._gate_pct(), 2)
                ch  = int(self.get_channel())
                tr  = int(self.get_transpose())
                sl  = bool(self.is_slave())
                running = bool(getattr(self.state, "is_running", False))

                # sequence signature (only content!)
                if self._chain_active:
                    seq_sig  = "CHAIN"
                    seq_list = None   # chain mode pushes via set_chain elsewhere
                else:
                    seq_list = self._build_seq()
                    seq_sig  = tuple(seq_list)

                # PARAMS: only send if params changed (never stop/start on tempo)
                params_sig = (t, s, gP, ch, tr, sl)
                if params_sig != self._prev_params_sig:
                    self._rt.set_params(
                        tempo=t, subdivision=s, gate=gP,
                        channel=ch, transpose=tr, slave_mode=sl,
                        immediate=False   # GUI already throttles; smooth glide
                    )
                    self._prev_params_sig = params_sig

                # SEQUENCE: only send when actual content changes (not when BPM moves)
                if not self._chain_active and seq_sig != self._prev_seq_sig:
                    self._rt.set_sequence(seq_list)
                    self._prev_seq_sig = seq_sig

                # Auto-kick only for “started empty then got notes” (non-slave)
                if running and getattr(self, "_armed_restart", False) and (seq_list and any(n != -1 for n in seq_list)) and not sl:
                    self._rt.start()
                    self._armed_restart = False

            except Exception:
                pass
            finally:
                time.sleep(0.05)
