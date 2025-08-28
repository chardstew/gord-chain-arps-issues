#!/usr/bin/env python3
"""
midi_csi.py — Korg-level minimal MIDI CSI logger.

- Listens to MIDI inputs you select (defaults try to catch "gord in"/"gord out" and IAC).
- Logs Start/Stop/Continue/Clock/Song Position and Note On/Off.
- Estimates BPM from MIDI Clock (24 ppqn), measures gate in ms & ticks,
  and computes gate% relative to the previous NoteOn→NoteOn tick span (step length).
- Infers "clock_active" (proxy for slave mode) if recent Clock seen.
- Press ENTER to stop; writes csi.csv.

Usage:
  python3 midi_csi.py                 # auto-pick ports (gord/IAC)
  python3 midi_csi.py --ports "gord in,gord out"
  python3 midi_csi.py --all           # open ALL input ports
  python3 midi_csi.py --list          # list ports and exit
  python3 midi_csi.py --csv my.csv

Requires:
  pip install mido python-rtmidi
"""

import argparse, csv, sys, time, threading, signal
from collections import deque, defaultdict
from typing import Dict, Tuple, List, Optional

try:
    import mido
except Exception as e:
    print("⚠️  mido not installed. Run: pip install mido python-rtmidi", file=sys.stderr)
    raise

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def nname(n: int) -> str:
    if n is None or n < 0 or n > 127: return ""
    return f"{NOTE_NAMES[n % 12]}{(n // 12) - 1}"

def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + f".{int((time.time()%1)*1000):03d}"

class CSIRecorder:
    def __init__(self, port_filters: List[str], open_all: bool, csv_path: str):
        self.csv_path = csv_path
        self.rows: List[Dict] = []
        self.lock = threading.Lock()

        # clock / tempo
        self.last_clock_t: Optional[float] = None
        self.clock_deltas = deque(maxlen=96)  # ~4 beats @ 24ppqn
        self.tick_count = 0
        self.clock_seen_ever = False

        # per (port,chan) step analysis
        self.last_noteon_tick: Dict[Tuple[str,int], int] = {}
        self.last_noteon_rowidx: Dict[Tuple[str,int], int] = {}

        # per note instance for gate calc
        self.note_on_map: Dict[Tuple[str,int,int], Tuple[int,float,int]] = {}  # (port, ch, note) -> (tick_at_on, mono_t, row_idx)

        # input ports
        self.inputs: List[mido.ports.BaseInput] = []
        self._open_ports(port_filters, open_all)

        # stop control
        self.stop_evt = threading.Event()
        self._stdin_thread = threading.Thread(target=self._wait_for_enter, daemon=True)
        self._stdin_thread.start()

    # ---------- ports ----------
    def _open_ports(self, filters: List[str], open_all: bool):
        names = mido.get_input_names()
        if not names:
            print("No MIDI input ports found.", file=sys.stderr)
            sys.exit(1)

        chosen = []
        if open_all:
            chosen = names
        elif filters:
            fl = [f.lower().strip() for f in filters if f.strip()]
            for n in names:
                ln = n.lower()
                if any(f in ln for f in fl):
                    chosen.append(n)
        else:
            # heuristic defaults: prefer ports containing 'gord' or 'iac'
            for n in names:
                ln = n.lower()
                if ('gord' in ln) or ('iac' in ln):
                    chosen.append(n)
            if not chosen:
                # fallback: everything (user can --list to pick better)
                chosen = names

        print("Listening on:")
        for n in chosen:
            print(f"  • {n}")
        print("Press ENTER to stop & write CSV.\n")

        for n in chosen:
            port = mido.open_input(n, callback=lambda msg, p=n: self._on_msg(msg, p))
            self.inputs.append(port)

    # ---------- stdin / stop ----------
    def _wait_for_enter(self):
        try:
            input()
        except EOFError:
            pass
        self.stop_evt.set()

    def wait(self):
        try:
            while not self.stop_evt.is_set():
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.stop_evt.set()
        finally:
            for p in self.inputs:
                try: p.close()
                except: pass
            self._flush_csv()

    # ---------- tempo helpers ----------
    def bpm_est(self) -> Optional[float]:
        if len(self.clock_deltas) == 0:
            return None
        # robust: median delta * 24 -> quarter note seconds
        d = sorted(self.clock_deltas)
        median = d[len(d)//2]
        if median <= 0: return None
        return 60.0 / (median * 24.0)

    def clock_active(self, horizon=1.0) -> int:
        # "slave-ish" if a clock tick happened in the last horizon seconds
        if self.last_clock_t is None: return 0
        return 1 if (time.monotonic() - self.last_clock_t) <= horizon else 0

    # ---------- message handling ----------
    def _on_msg(self, msg: mido.Message, port_name: str):
        t_wall = now_iso()
        t_mono = time.monotonic()

        # Maintain clock counters/tempo
        if msg.type == 'clock':
            self.clock_seen_ever = True
            self.tick_count += 1
            if self.last_clock_t is not None:
                self.clock_deltas.append(t_mono - self.last_clock_t)
            self.last_clock_t = t_mono
            # We don't log every clock tick (too spammy)
            return

        row = {
            "ts": t_wall,
            "t_mono": f"{t_mono:.6f}",
            "port": port_name,
            "event": msg.type,
            "status_hex": f"{msg.bytes()[0]:02X}" if hasattr(msg, "bytes") else "",
            "ch": getattr(msg, "channel", None if msg.type in ("start","stop","continue","songpos") else None),
            "note": getattr(msg, "note", None),
            "note_name": nname(getattr(msg, "note", None)) if hasattr(msg, "note") else "",
            "vel": getattr(msg, "velocity", None) if msg.type in ("note_on","note_off") else None,
            "cc": getattr(msg, "control", None) if msg.type == "control_change" else None,
            "value": getattr(msg, "value", None) if msg.type == "control_change" else None,
            "spp": getattr(msg, "pos", None) if msg.type == "songpos" else None,
            "tick": self.tick_count,
            "bpm_est": None,
            "clock_active": self.clock_active(),
            "step_ticks": None,
            "gate_ticks": None,
            "gate_ms": None,
            "gate_ratio": None,
            "gate_pct": None,
        }

        be = self.bpm_est()
        if be is not None:
            row["bpm_est"] = round(be, 3)

        printable = []

        if msg.type in ("start","stop","continue","songpos"):
            printable.append(f"[{port_name}] {msg.type.upper()}" + (f" pos={msg.pos}" if msg.type=="songpos" else ""))
            self._append_row(row, "ctl")
            print(" ".join(printable))
            return

        if msg.type == "note_on" and getattr(msg, "velocity", 0) == 0:
            # treat NoteOn vel=0 as NoteOff
            msg = mido.Message('note_off', note=msg.note, velocity=0, channel=msg.channel, time=msg.time)

        if msg.type == "note_on":
            ch = msg.channel + 1
            key_chan = (port_name, ch)
            key_note = (port_name, ch, msg.note)

            # Update previous note_on row's step length for this channel (NoteOn→NoteOn ticks)
            prev_tick = self.last_noteon_tick.get(key_chan)
            prev_row_idx = self.last_noteon_rowidx.get(key_chan)
            if prev_tick is not None and prev_row_idx is not None:
                step_ticks = max(0, self.tick_count - prev_tick)
                with self.lock:
                    self.rows[prev_row_idx]["step_ticks"] = step_ticks
                    # If gate already known, compute ratio/pct
                    gt = self.rows[prev_row_idx].get("gate_ticks")
                    if gt is not None and step_ticks > 0:
                        ratio = gt / float(step_ticks)
                        self.rows[prev_row_idx]["gate_ratio"] = round(ratio, 4)
                        self.rows[prev_row_idx]["gate_pct"] = round(ratio * 100.0, 2)

            # Log current ON
            self._append_row(row, "note")
            row_idx = len(self.rows) - 1
            self.last_noteon_tick[key_chan] = self.tick_count
            self.last_noteon_rowidx[key_chan] = row_idx
            self.note_on_map[key_note] = (self.tick_count, t_mono, row_idx)

            printable.append(f"[{port_name}] ch{ch} ON  {nname(msg.note):>3} v={msg.velocity:>3} tick={self.tick_count} bpm≈{row['bpm_est']}")
            print(" ".join(printable))
            return

        if msg.type == "note_off":
            ch = msg.channel + 1
            key_note = (port_name, ch, msg.note)
            on = self.note_on_map.pop(key_note, None)
            if on:
                on_tick, on_tmono, on_row_idx = on
                gate_ticks = max(0, self.tick_count - on_tick)
                gate_ms = max(0.0, (t_mono - on_tmono) * 1000.0)
                with self.lock:
                    self.rows[on_row_idx]["gate_ticks"] = gate_ticks
                    self.rows[on_row_idx]["gate_ms"] = round(gate_ms, 2)
                    st = self.rows[on_row_idx].get("step_ticks")
                    if isinstance(st, int) and st > 0:
                        ratio = gate_ticks / float(st)
                        self.rows[on_row_idx]["gate_ratio"] = round(ratio, 4)
                        self.rows[on_row_idx]["gate_pct"] = round(ratio * 100.0, 2)

            # Also add an explicit OFF row (for completeness)
            self._append_row(row, "note")
            printable.append(f"[{port_name}] ch{ch} OFF {nname(msg.note):>3} gate≈{gate_ms:.1f}ms (ticks={gate_ticks})")
            print(" ".join(printable))
            return

        # Other channel messages (if any) — record but keep console quiet
        self._append_row(row, "misc")

    # centralize row append so we keep a stable schema
    def _append_row(self, row: Dict, _tag: str):
        with self.lock:
            self.rows.append(row)

    # ---------- CSV ----------
    def _flush_csv(self):
        if not self.rows:
            print("No data captured; nothing to write.")
            return
        fields = ["ts","t_mono","port","event","status_hex",
                  "ch","note","note_name","vel","cc","value","spp",
                  "tick","bpm_est","clock_active",
                  "step_ticks","gate_ticks","gate_ms","gate_ratio","gate_pct"]
        try:
            with open(self.csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for r in self.rows:
                    w.writerow(r)
            print(f"\n✅ wrote {len(self.rows)} rows to {self.csv_path}")
        except Exception as e:
            print(f"❌ failed to write CSV: {e}", file=sys.stderr)

def list_ports_and_exit():
    ins = mido.get_input_names()
    outs = mido.get_output_names()
    print("MIDI Inputs:")
    for n in ins: print("  -", n)
    print("\nMIDI Outputs:")
    for n in outs: print("  -", n)
    sys.exit(0)

def main():
    ap = argparse.ArgumentParser(description="Minimal MIDI CSI logger")
    ap.add_argument("--ports", type=str, default="",
                    help="Comma-separated substrings to match input port names (case-insensitive).")
    ap.add_argument("--all", action="store_true", help="Open ALL input ports.")
    ap.add_argument("--list", action="store_true", help="List ports and exit.")
    ap.add_argument("--csv", type=str, default="csi.csv", help="Output CSV path.")
    args = ap.parse_args()

    if args.list:
        list_ports_and_exit()

    filters = [s.strip() for s in args.ports.split(",")] if args.ports else []
    rec = CSIRecorder(filters, args.all, args.csv)

    # graceful Ctrl-C
    signal.signal(signal.SIGINT, lambda *_: rec.stop_evt.set())
    signal.signal(signal.SIGTERM, lambda *_: rec.stop_evt.set())

    rec.wait()

if __name__ == "__main__":
    main()
