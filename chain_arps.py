# chain_arps.py
import tkinter as tk
from tkinter import simpledialog
from config import COLORS, NOTE_TO_COLOR
from utils import resource_path
from chain_runner import ChainRunner
from sequence_engine import SequenceGenerator


# Minimal ArpSnapshot template for now
def make_empty_snapshot():
    return {
        'root': None,
        'bpm': None,
        'scale': None,
        'scale_notes': [],
        'selected_intervals': [],
        'extension_octaves': {},
        'direction_mode': None,
        'gate_pct': None,
        'subdivision': None,
        'name': '',
        'loop_count': 1
    }


class ChainArpsWindow(tk.Toplevel):
    def __init__(self, master, state, midi_engine, on_change):
        super().__init__(master)
        self.title("CHAIN ARPS")
        self.configure(bg=COLORS['bg'])
        self.attributes('-topmost', True)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.bind('<Escape>', lambda e: self.withdraw())
        self.active_row_idx = None   # track current active row for red text
        self._pending_chain = None      # queued slots to install at loop boundary
        self._pending_index = None      # which slot is active when we apply



        self.state = state
        self.default_ticker_fg = COLORS['text']
        self.state.chain_arps_window = self 
        if not hasattr(self.state, "chain_global_loops"):
            self.state.chain_global_loops = "1"


        self.midi_engine = midi_engine
        self.on_change = on_change

        self.rows = []
        self.max_rows = 16

        # Init chain_arps_list if not already populated
        while len(self.state.chain_arps_list) < 8:
            self.state.chain_arps_list.append(None)

        self._build_ui()




    def _build_ui(self):
        # Main frame
        self.main_frame = tk.Frame(self, bg=COLORS['bg'])
        self.main_frame.pack(fill='both', expand=True, padx=12, pady=12)

        # Rows container
        self.rows_container = tk.Frame(self.main_frame, bg=COLORS['bg'])
        self.rows_container.pack(fill='both', expand=True)

        # --- Initial rows: one per snapshot that is *not* marked hidden ----------
        visible_snaps = [
            snap for snap in self.state.chain_arps_list
            if snap is not None and not snap.get('hidden', False)
        ]

        # Always show at least one row
        if not visible_snaps:
            visible_snaps = [None]

        for _ in visible_snaps:
            self._add_row()


                    
        # New Global Loop row at bottom
        global_loop_frame = tk.Frame(self.main_frame, bg=COLORS['bg'])
        global_loop_frame.pack(pady=(10, 4))

        tk.Label(global_loop_frame, text="Global:", fg=COLORS['text'], bg=COLORS['bg'],
                font=('Fixedsys', 18)).pack(side='left', padx=(0, 4))

        # default to "1" if blank/missing
        val = (getattr(self.state, "chain_global_loops", "") or "1")
        self.state.chain_global_loops = val

        self.global_loops_var = tk.StringVar(value=val)
        self.global_loops_var.trace_add("write", lambda *args: self._on_global_loops_change())
        tk.Entry(global_loop_frame, textvariable=self.global_loops_var, width=2,
                bg='black', fg='white', font=('Fixedsys', 18)).pack(side='left')

        # seed ticker to match the entry value
        disp = "X" if str(val).strip().lower() in ("x", "inf", "∞", "none") else str(val)
        self.global_ticker = tk.Label(global_loop_frame, text=f"0/{disp}",
                                    fg=COLORS['text'], bg=COLORS['bg'],
                                    font=('Fixedsys', 18))
        self.global_ticker.pack(side='left', padx=(8, 0))



        # Add/Remove buttons
        controls = tk.Frame(self.main_frame, bg=COLORS['bg'])
        controls.pack(pady=(6, 0))

        tk.Button(
            controls, text="+", width=2, command=self._add_row,
            bg=COLORS['button'], fg=COLORS['text']
        ).pack(side='left', padx=4)

        tk.Button(
            controls, text="–", width=2, command=self._remove_row,
            bg=COLORS['button'], fg=COLORS['text']
        ).pack(side='left', padx=4)
        
        # New row under controls — "chain_controls"
        chain_controls = tk.Frame(self.main_frame, bg=COLORS['bg'])
        chain_controls.pack(pady=(6, 4))
        
        tk.Button(
            chain_controls, text="Save", font=('Fixedsys', 10), width=8,
            command=self._on_save_list,
            bg=COLORS['button'], fg=COLORS['text']
        ).pack(side='left', padx=4)

        self.link_button = tk.Button(
            chain_controls, text="LINK", font=('Fixedsys', 10), width=8,
            command=self._toggle_link_mode,
            bg=COLORS['button'], fg=COLORS['text']
        )
        self.link_button.pack(side='left', padx=4)
        self._update_link_button_state()
        
        tk.Button(
            chain_controls, text="Load", font=('Fixedsys', 10), width=8,
            command=self._on_load_list,
            bg=COLORS['button'], fg=COLORS['text']
        ).pack(side='left', padx=4)
        
    def _build_slots_for_daemon(self):
        snaps = getattr(self.state, "chain_arps_list", []) or []
        solo_idxs = [i for i,s in enumerate(snaps) if s and not s.get("hidden") and s.get("solo")]

        slots = []
        for i, s in enumerate(snaps):
            if not s or s.get("hidden"):        continue
            if solo_idxs and not s.get("solo"): continue
            if s.get("muted"):                  continue

            # STRICT passthrough of the captured lane
            seq = s.get("sequence") or []
            notes = [-1 if (n is None or int(n) < 0) else int(n) for n in seq]

            # skip truly silent slots
            if not any(n >= 0 for n in notes):
                continue

            # loops = UI exact (None/X => infinite)
            raw = s.get("loop_count", 1)
            if raw is None:
                loops = -1
            else:
                try:    loops = max(1, int(str(raw).strip()))
                except: loops = 1

            slots.append({"notes": notes, "loops": loops})

        return slots




    def _emit_chain(self, start_index=0):
        slots = self._build_slots_for_daemon()
        try:
            self.midi_engine.play_chain(slots, index=int(start_index or 0))
        except Exception:
            pass

                

    def _compute_total_notes(self):
        sequence = SequenceGenerator(self.state).get_sequence_list()
        return sum(len(step['notes']) for step in sequence if isinstance(step, dict) and 'notes' in step)

    def _update_link_button_state(self):
        linked = (
            self.state.chain_mode_enabled
            and self.state.chain_runner is not None
            and self.state.chain_runner.running
        )
        if linked:
            self.link_button.config(
                text="UNLINK",
                bg='white',
                fg='black'
            )
        else:
            self.link_button.config(
                text="LINK",
                bg=COLORS['button'],
                fg=COLORS['text']
            )


        
    def _on_name_change(self, idx, name_var):
        # Push latest name into snapshot
        self.state.chain_arps_list[idx]['name'] = name_var.get()


    def _on_loops_change(self, idx, loops_var):
        val_str = (loops_var.get() or "").strip().lower()
        if val_str in ('x', 'none', ''):
            val, disp = 'X', 'X'         # None/inf in the runner
        else:
            try:
                val = max(1, int(val_str))
            except Exception:
                val = 1
            disp = val

        self.state.chain_arps_list[idx]['loop_count'] = val
        if idx < len(self.rows):
            self.rows[idx]['ticker_lbl'].config(text=f"0/{disp}")

        # make the runner pick up the new loop count
        self._refresh_and_save()


    def _on_global_loops_change(self):
        if getattr(self.state, "chain_emit_lock", False):
            return
        """Called whenever the Global loops entry changes."""
        self.state.chain_global_loops = self.global_loops_var.get().strip().lower()

        # Update preview ticker when NOT linked
        if not self.state.chain_mode_enabled:
            if hasattr(self, "global_ticker"):
                s = self.state.chain_global_loops
                if s in ("x", "inf", "∞", "none"):
                    self.global_ticker.config(text="0/X")
                elif s and s.isdigit() and int(s) > 0:
                    self.global_ticker.config(text=f"0/{int(s)}")
                else:
                    self.global_ticker.config(text="0/1")
            return

        # Linked: DO NOT re-arm chain while runner is live
        cr = getattr(self.state, "chain_runner", None)
        if cr and cr.running:
            # UI-only reflect the new total; audio remains unchanged
            if hasattr(self, "global_ticker"):
                total = cr.global_loops
                total_disp = "X" if total == float("inf") else str(int(total))
                self.global_ticker.config(text=f"{cr.global_loop_counter}/{total_disp}")
            return

        # Not running → safe to rebuild runner and arm once
        if cr:
            try: cr.stop()
            except Exception: pass
            self.state.chain_runner = None

        self.state.chain_runner = ChainRunner(
            self.state,
            self.midi_engine,
            self._update_ticker_for_row,
            self._on_chain_complete,
            global_loops=self.state.chain_global_loops,
        )
        self.state.chain_runner.rebuild_active_slots()

        # Reflect new global total immediately
        if hasattr(self, "global_ticker"):
            total = self.state.chain_runner.global_loops
            total_disp = "X" if total == float("inf") else str(int(total))
            self.global_ticker.config(text=f"0/{total_disp}")

        # Arm the daemon chain ONLY when stopped
        cur = getattr(self.state.chain_runner, "_cur_idx", None)
        self._emit_chain(start_index=(cur if cur is not None else 0))

            

    # ── ADD / BUILD A ROW ─────────────────────────────────────────────
    def _add_row(self):
        if len(self.rows) >= self.max_rows:
            return

        idx = len(self.rows)
        if idx >= len(self.state.chain_arps_list):
            self.state.chain_arps_list.append(None)

        row_frame = tk.Frame(self.rows_container, bg=COLORS['bg'])
        row_frame.pack(fill='x', pady=2)

        # --- First line: button frame ---------------------------------
        button_frame = tk.Frame(row_frame, bg=COLORS['bg'])
        button_frame.pack(fill='x')
        

        name_var = tk.StringVar(value=f"ARP {idx+1}")
        tk.Entry(button_frame, textvariable=name_var, width=12,
                 bg='black', fg='white', font=('Fixedsys', 18)).pack(side='left', padx=4)
        name_var.trace_add("write", lambda *args, idx=idx, nv=name_var: self._on_name_change(idx, nv))
        

        # Mute button
        mute_btn = tk.Button(button_frame, text="M", width=2,
                             state='disabled',
                             bg='gray25', fg='white', font=('Fixedsys', 10),
                             command=lambda rf=row_frame: self._on_mute_toggle(rf))
        mute_btn.pack(side='left', padx=2)

        # Solo button
        solo_btn = tk.Button(button_frame, text="S", width=2,
                             state='disabled',
                             bg='gray25', fg='white', font=('Fixedsys', 10),
                             command=lambda rf=row_frame: self._on_solo_toggle(rf))
        solo_btn.pack(side='left', padx=2)


        snap_btn = tk.Button(button_frame, text="Pull In", width=8,
                             command=lambda rf=row_frame: self._on_snap(rf),
                             bg=COLORS['button'], fg=COLORS['text'], font=('Fixedsys', 10))
        snap_btn.pack(side='left', padx=2)

        new_btn = tk.Button(button_frame, text="Clear", width=6,
                            command=lambda rf=row_frame: self._on_new(rf),
                            bg=COLORS['button'], fg=COLORS['text'], font=('Fixedsys', 10))
        new_btn.pack(side='left', padx=2)


        up_btn = tk.Button(button_frame, text="↑", width=2,
                           command=lambda rf=row_frame: self._move_row_up(rf),
                           bg=COLORS['button'], fg=COLORS['text'], font=('Fixedsys', 10))
        up_btn.pack(side='left', padx=2)

        down_btn = tk.Button(button_frame, text="↓", width=2,
                             command=lambda rf=row_frame: self._move_row_down(rf),
                             bg=COLORS['button'], fg=COLORS['text'], font=('Fixedsys', 10))
        down_btn.pack(side='left', padx=2)
         

        ticker_lbl = tk.Label(button_frame, text="0/1",
                              bg=COLORS['bg'], fg=COLORS['text'],
                              font=('Fixedsys', 18), width=6)
        ticker_lbl.pack(side='right', padx=4)
        loops_var = tk.StringVar(value='1')
        loops_entry = tk.Entry(button_frame, textvariable=loops_var, width=2,
                               bg='black', fg='white', font=('Fixedsys', 18))
        loops_entry.pack(side='right', padx=4)
        loops_var.trace_add("write", lambda *args, idx=idx, lv=loops_var: self._on_loops_change(idx, lv))


        # --- Second line: details frame ---------------------------------
        details_frame = tk.Frame(row_frame, bg=COLORS['bg'])
        details_frame.pack()

        details_lbl = tk.Text(details_frame, height=1, wrap='none',
                              bg=COLORS['bg'], fg=COLORS['text'],
                              font=('Fixedsys', 18), bd=0, highlightthickness=0)
        details_lbl.pack(fill='x', padx=4)
        details_lbl.configure(state='disabled')

        # --- Book-keeping ----------------------------------------------
        self.rows.append({
            'frame':       row_frame,
            'name_var':    name_var,
            'loops_var':   loops_var,
            'ticker_lbl':  ticker_lbl,
            'details_lbl': details_lbl,
            'mute_btn': mute_btn,
            'solo_btn': solo_btn,
            'idx':         idx
        })


        # Ensure there’s a snapshot to edit
        if self.state.chain_arps_list[idx] is None:
            self.state.chain_arps_list[idx] = make_empty_snapshot()
        # Row is now visible → never considered hidden
        self.state.chain_arps_list[idx]['hidden'] = False
        # If previously muted, unmute it now that row is visible again
        


        self._apply_snapshot_to_row(idx, self.state.chain_arps_list[idx])

        # 🔄 tell the runner & save
        self._refresh_and_save()



    

    def _remove_row(self):
        """
        Drumding-style hide:
        – removes the visible row
        – retains the snapshot in chain_arps_list (so it can be restored)
        – re-indexes the remaining rows, then refreshes the runner
        """
        if len(self.rows) <= 1:
            return  # do not remove the last visible row

        if not self.rows:
            return

        # 1) Which logical slot does the last GUI row point to?
        idx_removed = self.rows[-1]['idx']

        # 2) Remove the GUI row only
        row = self.rows.pop()
        row['frame'].destroy()

        # 3) Mute the matching snapshot so ChainRunner ignores it
        if idx_removed < len(self.state.chain_arps_list):
            snap = self.state.chain_arps_list[idx_removed]
            if snap is not None:
                snap['muted'] = True
                snap['hidden'] = True 


        # 4) Re-number remaining rows so their idx matches the list
        for new_idx, row in enumerate(self.rows):
            row['idx'] = new_idx

        # 5) Tell the runner + save
        self._refresh_and_save()

                        
    def _row_index(self, row_frame):
        for i, row in enumerate(self.rows):
            if row['frame'] == row_frame:
                return i
        return -1

    # ── Move rows up/down ──────────────────────────────────────

    def _move_row_up(self, row_frame):
        idx = self._row_index(row_frame)
        if idx > 0:
            self.rows[idx], self.rows[idx - 1] = self.rows[idx - 1], self.rows[idx]
            self.rows[idx]['idx'], self.rows[idx - 1]['idx'] = (
                self.rows[idx - 1]['idx'], self.rows[idx]['idx'])

            self.state.chain_arps_list[idx], self.state.chain_arps_list[idx - 1] = (
                self.state.chain_arps_list[idx - 1], self.state.chain_arps_list[idx])

            self._repack_rows()
            # 🔄 tell the runner & save
            self._refresh_and_save()


    def _move_row_down(self, row_frame):
        idx = self._row_index(row_frame)
        if idx < len(self.rows) - 1:
            self.rows[idx], self.rows[idx + 1] = self.rows[idx + 1], self.rows[idx]
            self.rows[idx]['idx'], self.rows[idx + 1]['idx'] = (
                self.rows[idx + 1]['idx'], self.rows[idx]['idx'])

            self.state.chain_arps_list[idx], self.state.chain_arps_list[idx + 1] = (
                self.state.chain_arps_list[idx + 1], self.state.chain_arps_list[idx])

            self._repack_rows()
            # 🔄 tell the runner & save
            self._refresh_and_save()


    def _repack_rows(self):
        for row in self.rows:
            row['frame'].pack_forget()
        for row in self.rows:
            row['frame'].pack(fill='x', pady=2)

    def _on_snap(self, row_frame):
        idx = self._row_index(row_frame)
        if idx < 0:
            return

        row = self.rows[idx]

        # Snapshot the subdivision as it is *now* (don’t let UI races mutate it mid-capture)
        subdiv = getattr(self.state, 'subdivision', None)
        if subdiv is None:
            subdiv = self.midi_engine.get_subdivision()

        # Parse per-slot loops from the UI
        raw = (row['loops_var'].get() or "").strip().lower()
        if raw in ('x', 'none', ''):
            loop_count = None
        else:
            try:
                loop_count = max(1, int(raw))
            except Exception:
                loop_count = 1

        # Build the static snapshot of musical state
        snapshot = {
            'root':               self.state.original_root,
            'bpm':                self.state.bpm,
            'scale':              self.state.scale or "None",
            'scale_notes':        list(getattr(self.state, 'scale_notes', set())),
            'selected_notes':     list(getattr(self.state, 'selected_notes', set())),
            'display_notes':      list(getattr(self.state, 'display_notes', [])) if hasattr(self.state, 'display_notes') else [],
            'selected_intervals': list(self.state.selected_intervals),
            'extension_octaves':  {k: list(v) for k, v in self.state.extension_octaves.items()},
            'direction_mode':     self.state.direction_mode,
            'gate_pct':           self.state.gate_pct,
            'subdivision':        int(subdiv),
            'name':               row['name_var'].get(),
            'loop_count':         loop_count,
            'build_mode_enabled': self.state.build_mode_enabled,
            'alt_seq_enabled':    self.state.alt_seq_enabled,
            'include_turnaround': self.state.include_turnaround,
            'diatonic_mode':      self.state.diatonic_mode,
        }

        # ==== PRO CAPTURE: take the *current audible pattern* exactly ====
        # Force a fresh build (avoids stale last_seq and guarantees direction/alt flags are applied)
        audible = SequenceGenerator(self.state).get_sequence_list() or []

        # Normalize to flat ints/None (no “helpful” edits; counts remain exact)
        flat = []
        for step in audible:
            if isinstance(step, dict) and 'notes' in step:
                nn = step['notes'][0] if step['notes'] else None
                flat.append(nn if (nn is None or isinstance(nn, int)) else None)
            else:
                flat.append(step if (step is None or isinstance(step, int)) else None)

        snapshot['sequence']    = flat
        snapshot['total_notes'] = sum(1 for n in flat if n is not None)

        # Save snapshot into the logical slot
        self.state.chain_arps_list[idx] = snapshot

        # Update the per-row ticker (UI only)
        row['ticker_lbl'].config(
            text=f"0/{snapshot['loop_count'] if snapshot['loop_count'] is not None else 'X'}"
        )

        # Single refresh + arm after snapshot is complete
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass
        self._refresh_and_save()

        # Details line (paint once)
        details_lbl = row['details_lbl']
        notes_list  = snapshot.get('display_notes') or snapshot.get('selected_notes') or snapshot.get('scale_notes') or []
        total_notes = snapshot.get('total_notes', 0)
        root        = snapshot.get('root')

        details_lbl.configure(state='normal')
        details_lbl.delete('1.0', tk.END)
        details_lbl.insert(tk.END, "Root: ")
        if root:
            details_lbl.insert(tk.END, root, root)
        details_lbl.insert(tk.END, f"  Scale: {snapshot.get('scale')}  ")
        details_lbl.insert(tk.END, f"Notes: ({total_notes}) ")
        for note in notes_list:
            details_lbl.insert(tk.END, note + ' ', note)
        for note in notes_list + ([root] if root else []):
            color = NOTE_TO_COLOR.get(note, COLORS['text'])
            details_lbl.tag_config(note, foreground=color)
        details_lbl.tag_configure("center", justify='center')
        details_lbl.tag_add("center", "1.0", "end")
        details_lbl.configure(state='disabled')



    def _on_chain_complete(self):
        runner = self.state.chain_runner
        finished = not (
            runner.global_loops == float('inf')
            or runner.global_loop_counter < runner.global_loops
        )

        if finished:
            # stop playback cleanly
            if self.midi_engine.is_slave():
                try:
                    self.midi_engine.stop_chain()   # can't stop host; silence chain
                except Exception:
                    pass
            else:
                if hasattr(self.master, "transport") and hasattr(self.master.transport, "_on_stop_click"):
                    self.master.after(0, self.master.transport._on_stop_click)  # stop transport so it’s ready to restart
                else:
                    try:
                        self.midi_engine.stop_chain()  # fallback: just silence the chain
                    except Exception:
                        pass

            # reset active-row highlight
            if self.active_row_idx is not None:
                for row in self.rows:
                    if row['idx'] == self.active_row_idx:
                        row['ticker_lbl'].config(fg=COLORS['text'])
                        break
                self.active_row_idx = None

        # update the GLOBAL ticker either way
        if hasattr(self, "global_ticker"):
            total = runner.global_loops
            total_disp = "X" if total == float("inf") else str(int(total))
            self.global_ticker.config(text=f"{runner.global_loop_counter}/{total_disp}")

        self.on_change()


    def _on_mute_toggle(self, row_frame):
        idx = self._row_index(row_frame)
        if idx < 0:
            return

        snap = self.state.chain_arps_list[idx]
        snap['muted'] = not snap.get('muted', False)

        btn = self.rows[idx]['mute_btn']
        if snap['muted']:
            btn.config(bg='red', fg='white')
        else:
            btn.config(bg='gray25', fg='white')

        # If unmuting and SOLO is active, clear SOLO (solo and mute are mutually exclusive)
        if not snap['muted'] and snap.get('solo'):
            snap['solo'] = False
            self.rows[idx]['solo_btn'].config(bg='gray25', fg='white')

        # Refresh slots
        self._refresh_and_save()

    def _on_solo_toggle(self, row_frame):
        idx = self._row_index(row_frame)
        if idx < 0:
            return

        snap = self.state.chain_arps_list[idx]
        snap['solo'] = not snap.get('solo', False)

        btn = self.rows[idx]['solo_btn']
        if snap['solo']:
            btn.config(bg='blue', fg='white')
            # If SOLO is now on, force MUTE off
            if snap.get('muted'):
                snap['muted'] = False
                self.rows[idx]['mute_btn'].config(bg='gray25', fg='white')
        else:
            btn.config(bg='gray25', fg='white')

        # Refresh slots
        self._refresh_and_save()


    def _on_new(self, row_frame):
        self._confirm_clear_row(row_frame)

    def _on_save_list(self, row_frame):
        print("[SAVE ROW] TODO: Save this list's data to file.")

    def _on_load_list(self, row_frame):
        print("[LOAD ROW] TODO: Load data into this list.")

    # ── Confirm Clear popup ───────────────────────────────────
    def _confirm_clear_row(self, row_frame):
        popup = tk.Toplevel(self)
        popup.title("")
        popup.configure(bg=COLORS['bg'])
        popup.attributes('-topmost', True)
        popup.resizable(False, False)

        x = self.winfo_rootx() + (self.winfo_width() // 2) - 100
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 50
        popup.geometry(f"200x100+{x}+{y}")

        tk.Label(
            popup, text="Are you sure?", font=("Arial", 10),
            fg=COLORS['text'], bg=COLORS['bg']
        ).pack(pady=(12, 8))

        btn_frame = tk.Frame(popup, bg=COLORS['bg'])
        btn_frame.pack(pady=(0, 8))

        yes_btn = tk.Button(
            btn_frame, text="Yes", width=8,
            command=lambda: (popup.destroy(), self._clear_row(row_frame))
        )
        yes_btn.pack(side='left', padx=8)

        no_btn = tk.Button(
            btn_frame, text="No", width=8,
            command=popup.destroy
        )
        no_btn.pack(side='left', padx=8)
        
    def _apply_snapshot_to_row(self, idx, snapshot):
        row = self.rows[idx]

        row['name_var'].set(snapshot.get('name') or f"ARP {idx+1}")
        row['loops_var'].set(snapshot.get('loop_count', 1))
        loop_count = snapshot.get('loop_count', 1)
        loop_disp = 'X' if loop_count in (None, 'X', 'x') or str(loop_count).strip().lower() in ('none', 'x') else loop_count
        row['ticker_lbl'].config(text=f"0/{loop_disp}")

        # Enable mute/solo buttons
        row['mute_btn'].config(state='normal')
        row['solo_btn'].config(state='normal')

        # Set button state visually
        if snapshot.get('muted', False):
            row['mute_btn'].config(bg='red', fg='white')
        else:
            row['mute_btn'].config(bg='gray25', fg='white')

        if snapshot.get('solo', False):
            row['solo_btn'].config(bg='blue', fg='white')
        else:
            row['solo_btn'].config(bg='gray25', fg='white')


        sub_val = snapshot.get('subdivision')
        sub_str = f"1/{sub_val}" if sub_val else "None"

        total_notes = snapshot.get('total_notes', 0)



        notes_list = snapshot.get('display_notes',
                                  snapshot.get('selected_notes',
                                               snapshot.get('scale_notes', [])))
        if notes_list:
            notes_disp = f"({total_notes}) " + " ".join(notes_list)
        else:
            notes_disp = f"({total_notes}) None"

        details_lbl = row['details_lbl']
        details_lbl.configure(state='normal')
        details_lbl.delete('1.0', tk.END)

        # Build display line — same as in _on_snap
        details_lbl.insert(tk.END, "Root: ")
        root = snapshot.get('root')
        if root:
            details_lbl.insert(tk.END, root, root)
        details_lbl.insert(tk.END, f" Scale: {snapshot.get('scale')}  ")
        details_lbl.insert(tk.END, f"Notes: ({total_notes}) ")


        # Set tags for each note
        for note in notes_list + ([root] if root else []):
            color = NOTE_TO_COLOR.get(note, COLORS['text'])
            details_lbl.tag_config(note, foreground=color)
            
        details_lbl.tag_configure("center", justify='center')
        details_lbl.tag_add("center", "1.0", "end")


        details_lbl.configure(state='disabled')


    def _refresh_and_save(self):
        """
        Commit UI edits -> rebuild runner slots -> update daemon safely.
        If LINKed & running, we DO NOT re-arm the chain immediately.
        Instead we queue it to be applied at the next loop boundary
        (handled in _update_ticker_for_row when current_loop == 1).
        """
        # 1) notify state/UI
        if self.on_change:
            try: self.on_change()
            except Exception: pass

        cr = getattr(self.state, "chain_runner", None)

        # 2) keep runner fresh
        if cr:
            try: cr.rebuild_active_slots()
            except Exception: pass

        # 3) 🔒 don’t push to daemon while LINK setup is locked
        if getattr(self.state, "chain_emit_lock", False):
            return

        if not getattr(self.state, "chain_mode_enabled", False):
            return

        # build latest slots
        slots = self._build_slots_for_daemon()
        cur   = getattr(cr, "_cur_idx", 0) if cr else 0

        # If chain runner is live, defer install to loop boundary
        if cr and getattr(cr, "running", False):
            self._pending_chain = slots
            self._pending_index = cur  # best effort starting index
            return

        # If LINKed but runner not running, safe to arm immediately
        try:
            self.midi_engine.play_chain(slots, index=int(cur or 0))
        except Exception:
            pass


    def _clear_row(self, row_frame):
        idx = self._row_index(row_frame)
        if idx >= 0:
            self.state.chain_arps_list[idx] = make_empty_snapshot()
            self._apply_snapshot_to_row(idx, self.state.chain_arps_list[idx])
            

    # ──────────────────────────────────────────────────────────────
    #  Utility: commit UI edits & refresh the runner
    # ──────────────────────────────────────────────────────────────
    def _update_ticker_for_row(self, slot_idx, current_loop, total_loops, is_active=True):
        # normalize display for "X"/None
        loop_disp = total_loops if isinstance(total_loops, str) else ('X' if total_loops is None else total_loops)

        def apply():
            # 1) revert previously highlighted row (if any)
            if self.active_row_idx is not None and self.active_row_idx != slot_idx:
                for r in self.rows:
                    if r['idx'] == self.active_row_idx:
                        r['ticker_lbl'].config(fg=self.default_ticker_fg)
                        break

            # 2) paint current row + update its ticker
            for row in self.rows:
                if row['idx'] == slot_idx:
                    row['ticker_lbl'].config(
                        text=f"{current_loop}/{loop_disp}",
                        fg=NOTE_TO_COLOR.get('C', 'red') if is_active else COLORS['text']
                    )
                    self.active_row_idx = slot_idx
                    break

            # 3) update GLOBAL ticker (if runner present)
            cr = getattr(self.state, "chain_runner", None)
            if cr and hasattr(self, "global_ticker"):
                total = cr.global_loops
                total_disp = "X" if total == float("inf") else str(int(total))
                try:
                    self.global_ticker.config(text=f"{cr.global_loop_counter}/{total_disp}")
                except Exception:
                    pass

            # 4) 🔒 Deferred chain (re)install at SAFE boundary:
            #     only when a new pass of the active slot begins (current_loop == 1)
            #     and we have queued edits to apply.
            if is_active and current_loop == 1 and getattr(self, "_pending_chain", None) is not None:
                slots = self._pending_chain
                idx   = self._pending_index if self._pending_index is not None else slot_idx

                # clear queue BEFORE emit to avoid re-entrancy/races
                self._pending_chain = None
                self._pending_index = None

                try:
                    # install once at loop boundary so the daemon restarts cleanly
                    self.midi_engine.play_chain(slots, index=int(idx or 0))
                except Exception:
                    pass

        try:
            self.after(0, apply)
        except RuntimeError:
            # window may be closing; apply inline
            apply()


    def _toggle_link_mode(self):
        if not self.state.chain_mode_enabled:
            # LINK ON
            self.state.chain_mode_enabled = True
            self.link_button.config(text="UNLINK", bg='white', fg='black')

            # Atomic LINK setup: block any incidental emits until done
            self.state.chain_emit_lock = True
            try:
                # capture globals & current transport subdivision
                raw = self.global_loops_var.get().strip().lower()
                self.state.chain_global_loops = raw
                self.state.transport_subdivision = self.midi_engine.get_subdivision()

                # (re)create runner
                self.state.chain_runner = ChainRunner(
                    self.state, self.midi_engine,
                    self._update_ticker_for_row, self._on_chain_complete,
                    global_loops=raw
                )
                self.state.chain_runner.rebuild_active_slots()

                # Build whatever exists right now (no auto Pull-In)
                slots = self._build_slots_for_daemon()

                # Reflect global loop target in the UI
                if hasattr(self, "global_ticker"):
                    total = self.state.chain_runner.global_loops
                    total_disp = "X" if total == float("inf") else str(int(total))
                    self.global_ticker.config(text=f"0/{total_disp}")

                # Arm the daemon ONLY IF there are slots (once!)
                if slots:
                    self.midi_engine.play_chain(slots, index=0)

                    # Start runner only if transport is running or we’re slaved
                    if getattr(self.state, "is_running", False) or self.midi_engine.is_slave():
                        self.state.chain_runner.start()

            except Exception:
                pass
            finally:
                self.state.chain_emit_lock = False

        else:
            # LINK OFF (unchanged)
            self.state.chain_mode_enabled = False
            self.link_button.config(text="LINK", bg=COLORS['button'], fg=COLORS['text'])
            try:
                self.midi_engine.stop_chain()
            except Exception:
                pass
            cr = getattr(self.state, "chain_runner", None)
            if cr:
                try: cr.stop()
                except Exception: pass
            self.state.chain_runner = None

        # notify settings changed
        self.on_change()





# END ChainArpsWindow

