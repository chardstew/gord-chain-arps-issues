# config.py

# ── Musical Constants ─────────────────────────────────────────
NOTE_NAMES = [
    'C',  'C#', 'D',  'D#', 'E',  'F',  'F#', 'G',  'G#', 'A',  'A#', 'B'
]

# Interval labels for 0–12 semitone steps
INTERVAL_LABELS = {
    0: "P1", 1: "m2", 2: "M2", 3: "m3", 4: "M3", 5: "P4",
    6: "TT", 7: "P5", 8: "m6", 9: "M6", 10: "m7", 11: "M7", 12: "P8"
}

# Enharmonic display names (when needed)
ENHARMONIC = {
    0: "C", 1: "C#/Db", 2: "D", 3: "D#/Eb", 4: "E", 5: "F",
    6: "F#/Gb",7: "G", 8: "G#/Ab", 9: "A", 10: "A#/Bb", 11: "B"
}

# ── Color map per note name ─────────────────────────────────────────
NOTE_TO_COLOR = {
    'C' :  '#D12C2C',   # red
    'C#':  '#EB7916',   # orange
    'D' :  '#C7A72F',   # gold
    'D#':  '#E4DC00',   # yellow
    'E' :  '#A8E000',   # lime
    'F' :  '#32B643',   # green
    'F#':  '#1E5B3E',   # pine
    'G' :  '#00C8B3',   # teal
    'G#':  '#2F5BFF',   # blue
    'A' :  '#8E38FF',   # purple
    'A#':  '#653E7B',   # plum
    'B' :  '#AB2579',   # wine
}





# Friendly names / tooltips for intervals
INTERVAL_NICKNAMES = {
    0: "Root/Unison", 1: "b9", 2: "9", 3: "b3, A2, #9",
    4: "3rd", 5: "4th/11", 6: "A4, #11, d5, b5", 7: "5th",
    8: "b13, A5, #5", 9: "6th/13", 10: "b7", 11: "7th", 12: "8ve"
}

# ── UI Color Palette ──────────────────────────────────────────
COLORS = {
    'bg':       'black',
    'text':     'white',
    'highlight':'#FDE8AC',
    'off':      '#666666',
    'on':       '#00ff00',
    'half':     '#008800',
    'disabled':'#111111',
    'button':   '#222222'
}

# ── UI Scaling ────────────────────────────────────────────────
CELL_WIDTH  = 4      # width in text units
CELL_HEIGHT = 2      # height in text units
CELL_PAD    = 1      # padding in pixels
GRID_COLS   = 9      # octave columns 0–8
# Total pixel width for grids & canvas
GRID_WIDTH_PX = GRID_COLS * (CELL_WIDTH * 7 + 2 * CELL_PAD)

# ── Sequencer Defaults ───────────────────────────────────────
DEFAULT_TEMPO       = 120  # BPM
DEFAULT_GATE        = 80   # %
DEFAULT_SUBDIVISION = 4    # quarter notes
MAX_OCTAVE          = 8    # 0–8
MIDI_PORT_NAME      = 'gord 1'  # loopMIDI port prefix

GRID_FONT = ("Fixedsys", 10)

# Give flats the same colors as their enharmonic sharps:
for semitone, pair in ENHARMONIC.items():
    if "/" in pair:
        sharp, flat = pair.split("/")
        NOTE_TO_COLOR[flat] = NOTE_TO_COLOR[sharp]

