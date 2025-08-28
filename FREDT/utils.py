# utils.py

def hex_to_rgb(hex_color):
    """Convert #RRGGBB to tuple of ints (R, G, B)."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_contrast_text_color(hex_color):
    """Return black or white depending on brightness of bg color."""
    r, g, b = hex_to_rgb(hex_color)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return '#000000' if luminance > 128 else '#ffffff'

# note_utils.py

from config import NOTES

def note_index(note):
    return NOTES.index(note)

def shift_note(note, semitones):
    return NOTES[(note_index(note) + semitones) % 12]
