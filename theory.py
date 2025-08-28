import json
import os

# Paths to JSON data files (assumed in same directory)
_base_dir = os.path.dirname(__file__)
_scales_path = os.path.join(_base_dir, 'scales.json')
_chords_path = os.path.join(_base_dir, 'chords.json')

# Load scales data
with open(_scales_path, 'r') as f:
    _scales_json = json.load(f)
    _raw_scales = _scales_json.get('scales', {})
    



# Load chords and intervals data
with open(_chords_path, 'r') as f:
    _chords_json = json.load(f)
    _raw_chords = _chords_json.get('chords', {})
    INTERVALS = _chords_json.get('intervals', {})


def _resolve_aliases(raw_data: dict) -> dict:
    """
    Resolve alias_of entries in raw_data so every key maps to its final intervals,
    length, and display_name.
    """
    resolved = {}
    for key, entry in raw_data.items():
        target = entry.get('alias_of', key)
        base = raw_data.get(target, {})
        resolved[key] = {
            'intervals': base.get('intervals', []),
            'length': base.get('length', len(base.get('intervals', []))),
            'display_name': entry.get('display_name', base.get('display_name', key))
        }
    return resolved
    

# Final lookup tables
SCALES = _resolve_aliases(_raw_scales)
CHORDS = _resolve_aliases(_raw_chords)


def get_scale_keys(order: str = 'length_then_alpha') -> list:
    """
    Return a list of scale keys ordered by length then display_name (alphabetical).
    """
    items = list(SCALES.items())
    if order == 'length_then_alpha':
        items.sort(key=lambda kv: (kv[1]['length'], kv[1]['display_name']))
    return [k for k, _ in items]


def get_chord_keys(order: str = 'length_then_alpha') -> list:
    """
    Return a list of chord keys ordered by length then display_name (alphabetical).
    """
    items = list(CHORDS.items())
    if order == 'length_then_alpha':
        items.sort(key=lambda kv: (kv[1]['length'], kv[1]['display_name']))
    return [k for k, _ in items]

# Build note name -> semitone map for chord parsing
def _build_note_map(note_names):
    return {name: idx for idx, name in enumerate(note_names)}

# Lazy import of NOTE_NAMES from config
try:
    from config import NOTE_NAMES
    NOTE_TO_SEMITONE = _build_note_map(NOTE_NAMES)
except ImportError:
    NOTE_TO_SEMITONE = {}


def parse_chord_string(chord_str: str) -> tuple:
    """
    Parse strings like 'Cmaj7/E' or 'Dmin' into (root, chord_key, bass) components.
    """
    if '/' in chord_str:
        chord_part, bass = chord_str.split('/', 1)
    else:
        chord_part, bass = chord_str, None

    root = chord_part[:2] if chord_part[1:2] in ('#', 'b') else chord_part[:1]
    key = chord_part[len(root):]
    return root, key, bass


def chord_with_slash_intervals(chord_str: str) -> tuple:
    """
    Given 'Cmaj7/E', returns ([0,4,7,11], [4])
    First list is chord intervals relative to root;
    second is bass-interval list if slash present.
    """
    root, key, bass = parse_chord_string(chord_str)
    base = CHORDS.get(key, {}).get('intervals', [])
    bass_list = []
    if bass and NOTE_TO_SEMITONE:
        root_val = NOTE_TO_SEMITONE.get(root)
        bass_val = NOTE_TO_SEMITONE.get(bass)
        if root_val is not None and bass_val is not None:
            offset = (bass_val - root_val) % 12
            bass_list = [offset]
    return base, bass_list
