# config.py

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

NOTE_TO_COLOR = {
    'C':  '#D12C2C',
    'C#': '#EB7916',
    'D':  '#C7A72F',
    'D#': '#E4DC00',
    'E':  '#A8E000',
    'F':  '#32B643',
    'F#': '#1E5B3E',
    'G':  '#00C8B3',
    'G#': '#2F5BFF',
    'A':  '#8E38FF',
    'A#': '#653E7B',
    'B':  '#AB2579'
}

COLORS = {
    'bg': '#000000',
    'fg': '#FFFFFF',
    'muted': '#444444'
}

SCALES = {
    "major": {
        "intervals": [0, 2, 4, 5, 7, 9, 11],
        "length": 7,
        "display_name": "Major"
    },
    "natural_minor": {
        "intervals": [0, 2, 3, 5, 7, 8, 10],
        "length": 7,
        "display_name": "Minor"
    },
    "altered": {
        "intervals": [0, 1, 3, 4, 6, 8, 10],
        "length": 7,
        "display_name": "Altered"
    },
    "bebop_dominant": {
        "intervals": [0, 2, 4, 5, 7, 9, 10, 11],
        "length": 8,
        "display_name": "Bebop Dominant"
    },
    "bebop_major": {
        "intervals": [0, 2, 4, 5, 7, 8, 9, 11],
        "length": 8,
        "display_name": "Bebop Major"
    },
    "bebop_minor": {
        "intervals": [0, 2, 3, 5, 7, 8, 10, 11],
        "length": 8,
        "display_name": "Bebop Minor"
    },
    "blues": {
        "intervals": [0, 3, 5, 6, 7, 10],
        "length": 6,
        "display_name": "Blues"
    },
    "diminished": {
        "intervals": [0, 2, 3, 5, 6, 8, 9, 11],
        "length": 8,
        "alias_of": "octatonic_whole_half",
        "display_name": "Diminished"
    },
    "dorian_b2": {
        "intervals": [0, 1, 3, 5, 7, 9, 10],
        "length": 7,
        "display_name": "Dorian b2"
    },
    "dorian_sharp4": {
        "intervals": [0, 2, 3, 6, 7, 9, 10],
        "length": 7,
        "display_name": "Dorian #4"
    },
    "double_harmonic": {
        "intervals": [0, 1, 4, 5, 7, 8, 11],
        "length": 7,
        "display_name": "Double Harmonic"
    },
    "egyptian": {
        "intervals": [0, 2, 5, 7, 10],
        "length": 5,
        "display_name": "Egyptian"
    },
    "harmonic_minor": {
        "intervals": [0, 2, 3, 5, 7, 8, 11],
        "length": 7,
        "display_name": "Harmonic Minor"
    },
    "hungarian_minor": {
        "intervals": [0, 2, 3, 6, 7, 8, 11],
        "length": 7,
        "display_name": "Hungarian Minor"
    },
    "indian_pancham": {
        "intervals": [0, 2, 3, 5, 7, 8, 10],
        "length": 7,
        "display_name": "Indian Pancham"
    },
    "ionian_sharp5": {
        "intervals": [0, 2, 4, 5, 8, 9, 11],
        "length": 7,
        "display_name": "Ionian #5"
    },
    "japanese_in": {
        "intervals": [0, 1, 5, 7, 10],
        "length": 5,
        "display_name": "Japanese In"
    },
    "japanese_yo": {
        "intervals": [0, 2, 3, 7, 8],
        "length": 5,
        "display_name": "Japanese Yo"
    },
    "lydian_augmented": {
        "intervals": [0, 2, 4, 6, 8, 9, 11],
        "length": 7,
        "display_name": "Lydian Augmented"
    },
    "lydian_dominant": {
        "intervals": [0, 2, 4, 6, 7, 9, 10],
        "length": 7,
        "display_name": "Lydian Dominant"
    },
    "lydian_sharp2": {
        "intervals": [0, 2, 4, 6, 8, 9, 11],
        "length": 7,
        "display_name": "Lydian #2"
    },
    "major_blues": {
        "intervals": [0, 2, 3, 4, 7, 9],
        "length": 6,
        "display_name": "Major Blues"
    },
    "major_pentatonic": {
        "intervals": [0, 2, 4, 7, 9],
        "length": 5,
        "display_name": "Major Pentatonic"
    },
    "melodic_minor": {
        "intervals": [0, 2, 3, 5, 7, 9, 11],
        "length": 7,
        "display_name": "Melodic Minor"
    },
    "minor_pentatonic": {
        "intervals": [0, 3, 5, 7, 10],
        "length": 5,
        "display_name": "Minor Pentatonic"
    },
    "mixolydian_b6": {
        "intervals": [0, 2, 4, 5, 7, 8, 10],
        "length": 7,
        "display_name": "Mixolydian b6"
    },
    "neapolitan_major": {
        "intervals": [0, 1, 3, 5, 7, 9, 11],
        "length": 7,
        "display_name": "Neapolitan Major"
    },
    "neapolitan_minor": {
        "intervals": [0, 1, 3, 5, 7, 8, 11],
        "length": 7,
        "display_name": "Neapolitan Minor"
    },
    "octatonic_half_whole": {
        "intervals": [0, 1, 3, 4, 6, 7, 9, 10],
        "length": 8,
        "display_name": "Octatonic (Half-Whole)"
    },
    "octatonic_whole_half": {
        "intervals": [0, 2, 3, 5, 6, 8, 9, 11],
        "length": 8,
        "display_name": "Octatonic (Whole-Half)"
    },
    "oriental": {
        "intervals": [0, 1, 4, 5, 6, 8, 10, 11],
        "length": 8,
        "display_name": "Oriental"
    },
    "persian": {
        "intervals": [0, 1, 4, 5, 6, 8, 9, 11],
        "length": 8,
        "display_name": "Persian"
    },
    "phrygian_dominant": {
        "intervals": [0, 1, 4, 5, 7, 8, 10],
        "length": 7,
        "display_name": "Phrygian Dominant"
    },
    "prometheus": {
        "intervals": [0, 2, 4, 6, 9, 10],
        "length": 6,
        "display_name": "Prometheus"
    },
    "spanish_gypsy": {
        "intervals": [0, 1, 4, 5, 7, 8, 10],
        "length": 7,
        "alias_of": "phrygian_dominant",
        "display_name": "Spanish Gypsy"
    },
    "super_locrian_bb7": {
        "intervals": [0, 1, 3, 4, 6, 8, 9],
        "length": 7,
        "display_name": "Super Locrian bb7"
    },
    "whole_tone": {
        "intervals": [0, 2, 4, 6, 8, 10],
        "length": 6,
        "display_name": "Whole Tone"
    },
    "ionian": {
        "intervals": [0, 2, 4, 5, 7, 9, 11],
        "length": 7,
        "alias_of": "major",
        "display_name": "Ionian"
    },
    "dorian": {
        "intervals": [0, 2, 3, 5, 7, 9, 10],
        "length": 7,
        "display_name": "Dorian"
    },
    "phrygian": {
        "intervals": [0, 1, 3, 5, 7, 8, 10],
        "length": 7,
        "display_name": "Phrygian"
    },
    "lydian": {
        "intervals": [0, 2, 4, 6, 7, 9, 11],
        "length": 7,
        "display_name": "Lydian"
    },
    "mixolydian": {
        "intervals": [0, 2, 4, 5, 7, 9, 10],
        "length": 7,
        "display_name": "Mixolydian"
    },
    "aeolian": {
        "intervals": [0, 2, 3, 5, 7, 8, 10],
        "length": 7,
        "alias_of": "natural_minor",
        "display_name": "Aeolian"
    },
    "locrian": {
        "intervals": [0, 1, 3, 5, 6, 8, 10],
        "length": 7,
        "display_name": "Locrian"
    }
}


TUNINGS = [
    { "name": "Standard (E A D G B E)",            "strings": ["E", "A", "D", "G", "B", "E"] },
    { "name": "Half‑Step Down (D# G# C# F# A# D#)", "strings": ["D#", "G#", "C#", "F#", "A#", "D#"] },
    { "name": "All Fourths (E A D G C F)", "strings": ["E", "A", "D", "G", "C", "F"] },
    { "name": "Drop D (D A D G B E)",              "strings": ["D", "A", "D", "G", "B", "E"] },
    { "name": "Drop C (C G C F A D)",              "strings": ["C", "G", "C", "F", "A", "D"] },
    { "name": "DADGAD (D A D G A D)",              "strings": ["D", "A", "D", "G", "A", "D"] },
    { "name": "Open G (D G D G B D)",              "strings": ["D", "G", "D", "G", "B", "D"] },
    { "name": "Open D (D A D F# A D)",             "strings": ["D", "A", "D", "F#", "A", "D"] },
    { "name": "Open C (C G C G C E)",              "strings": ["C", "G", "C", "G", "C", "E"] },
    { "name": "Baritone B (B E A D F# B)",         "strings": ["B", "E", "A", "D", "F#", "B"] }
]

NUM_FRETS = 24
