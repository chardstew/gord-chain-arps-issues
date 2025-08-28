# state.py

class AppState:
    def __init__(self):
        self.root = 0
        self.scale = 0
        self.tuning = 0
        self.chord = None
        self.chord_keys = []
        self.mode = "scale"  # "scale" or "chord"

        
    def get_root_note_index(self):
        return self.root

    def get_selected_scale(self):
        return self.scale

    def get_selected_tuning(self):
        return self.tuning

    def update(self, root=None, scale=None, tuning=None, chord=None, mode=None):
        if root is not None:
            self.root = root
        if scale is not None:
            self.scale = scale
        if tuning is not None:
            self.tuning = tuning
        if chord is not None:
            self.chord = chord
        if mode is not None:
            self.mode = mode

            
    def reset(self):
        self.root = 0
        self.scale = 0
        self.tuning = 0
        self.chord = None
        self.mode = "scale"

