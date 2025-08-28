#piano_panel.py

import tkinter as tk
from config import NOTE_NAMES, NOTE_TO_COLOR, COLORS, GRID_WIDTH_PX

class PianoPanel(tk.Frame):
    """
    Displays a large, colored root-note label plus a fixed-width 7-key piano
    canvas that always matches the interval grid’s width.
    """
    def __init__(self, master, state, on_note_click):
        super().__init__(master, bg=COLORS['bg'])
        self.state = state
        self.on_note_click = on_note_click
        
        self._blink_after_id = None 

        # Horizontal container: [ Root Label | Piano Canvas ]
        container = tk.Frame(self, bg=COLORS['bg'])
        container.pack(anchor='center')

        # Large root-note label
        self.root_label = tk.Label(
            container,
            text="",
            width=2,
            font=('Fixedsys', 28),
            bg=COLORS['bg'],
            fg=COLORS['text']
        )
        self.root_label.pack(side='left', padx=(0, 20))

        # Piano canvas: exactly GRID_WIDTH_PX wide
        self.canvas_width = GRID_WIDTH_PX
        self.canvas = tk.Canvas(
            container,
            width=self.canvas_width,
            height=160,
            bg=COLORS['bg'],
            highlightthickness=0
        )
        self.canvas.pack(side='left')
        self.canvas.bind("<Button-1>", self._on_click)

        # Internal maps for redrawing
        self.note_to_rect = {}
        self.normal_fill = {}
        self.white_pos = []
        self.black_pos = []

        # Initial draw
        self._draw_keys()
        self.redraw()

    def _draw_keys(self):
        """Draw the 7 white + 5 black keys on the canvas."""
        self.canvas.delete('all')
        self.note_to_rect.clear()
        self.normal_fill.clear()
        self.white_pos.clear()
        self.black_pos.clear()

        # Compute key dimensions
        total_white = 7
        white_w = self.canvas_width // total_white
        white_h = 160
        black_w = int(white_w * 0.6)
        black_h = 100

        # Draw white keys C–B
        x = 0
        for note in ['C','D','E','F','G','A','B']:
            rect = self.canvas.create_rectangle(
                x, 0, x + white_w, white_h,
                fill='white', outline='black', width=2
            )
            self.white_pos.append((note, rect, x, 0, white_w, white_h))
            self.note_to_rect[note] = rect
            self.normal_fill[note] = 'white'
            x += white_w

        # Draw black keys at appropriate offsets
        black_map = [('C#', 0), ('D#', 1), ('F#', 3), ('G#', 4), ('A#', 5)]
        for note, idx in black_map:
            # extract x-position and width of white key idx
            _, _, wx, _, wW, _ = self.white_pos[idx]
            bx = wx + int(wW * 0.75)
            rect = self.canvas.create_rectangle(
                bx, 0, bx + black_w, black_h,
                fill='black', outline='black'
            )
            self.black_pos.append((note, rect, bx, 0, black_w, black_h))
            self.note_to_rect[note] = rect
            self.normal_fill[note] = 'black'

    def _pick_note(self, x, y):
        """Return the note name whose key contains (x,y), preferring black keys."""
        for note, rect, rx, ry, w, h in self.black_pos:
            if rx <= x <= rx + w and ry <= y <= ry + h:
                return note
        for note, rect, rx, ry, w, h in self.white_pos:
            if rx <= x <= rx + w and ry <= y <= ry + h:
                return note
        return None

    def _on_click(self, event):
        """Invoke the callback with the clicked note name."""
        note = self._pick_note(event.x, event.y)
        if note:
            self.on_note_click(note)

    def redraw(self):
        """
        Recolor keys according to state.selected_notes, and update
        the large root-label’s text and color.
        """
        # Update root label
        root_note = next(iter(self.state.selected_notes), "")
        self.root_label.config(
            text=root_note,
            fg=NOTE_TO_COLOR.get(root_note, COLORS['text'])
        )

        # Recolor each key
        for note, rect in self.note_to_rect.items():
            if (
                note in self.state.selected_notes               # original root(s)
                or (self.state.build_mode_enabled               # ← NEW: show preview
                    and note == self.state.playback_root)
            ):
                fill = NOTE_TO_COLOR.get(note, self.normal_fill[note])
            else:
                fill = self.normal_fill[note]
            self.canvas.itemconfig(rect, fill=fill)

            
    def _blink_original(self):
        cond = (self.state.build_mode_enabled
                and self.state.playback_root
                and self.state.playback_root != self.state.original_root)
        if cond:
            rect = self.note_to_rect[self.state.original_root]
            cur  = self.canvas.itemcget(rect, 'fill')
            base = self.normal_fill[self.state.original_root]
            flash = NOTE_TO_COLOR[self.state.original_root]
            self.canvas.itemconfig(rect, fill = flash if cur == base else base)

            period = int(60000 / max(1, self.state.bpm))
            self._blink_after_id = self.after(period, self._blink_original)
        else:
            if self._blink_after_id:
                self.after_cancel(self._blink_after_id)
                self._blink_after_id = None
            # restore steady colour
            rect = self.note_to_rect[self.state.original_root]
            steady = (NOTE_TO_COLOR[self.state.original_root]
                      if self.state.original_root in self.state.selected_notes
                      else self.normal_fill[self.state.original_root])
            self.canvas.itemconfig(rect, fill=steady)


