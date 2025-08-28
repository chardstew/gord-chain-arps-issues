import os
import datetime
import tkinter.filedialog as fd
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

# Global export folder (set via choose_export_folder)
export_folder = None


def choose_export_folder():
    """Prompt the user to select an export directory."""
    global export_folder
    folder = fd.askdirectory()
    if folder:
        export_folder = folder
    return folder


def export_arp_sequence(
    seq,
    bpm,
    gate_pct,
    subdivision,
    dest_folder=None
):
    folder = dest_folder or export_folder
    if not folder or not seq:
        return

    mid = MidiFile(type=0, ticks_per_beat=960)
    track = MidiTrack()
    mid.tracks.append(track)

    # tempo meta message at t=0
    track.append(MetaMessage(
        'set_tempo',
        tempo=mido.bpm2tempo(bpm),
        time=0
    ))

    # timing
    ppq = mid.ticks_per_beat
    ticks_per_div = ppq * 4 // subdivision
    gate_ticks    = int(ticks_per_div * gate_pct / 100)
    rest_ticks    = ticks_per_div - gate_ticks

    for note in seq:
        if note is not None:
            n_out = note + 12
            if 0 <= n_out <= 127:
                track.append(Message('note_on',  note=n_out, velocity=100, time=0))
                track.append(Message('note_off', note=n_out, velocity=0,   time=gate_ticks))
        # advance to next step
        delay = rest_ticks if note is not None else ticks_per_div
        if delay > 0:
            track.append(Message('note_on', note=0, velocity=0, time=delay))

    # filename
    date_str = datetime.datetime.now().strftime("%Y%b%d")
    counter = 1
    while True:
        fn = f"{date_str}_ARP_{counter:03d}.mid"
        path = os.path.join(folder, fn)
        if not os.path.exists(path):
            break
        counter += 1

    mid.save(path)


def export_chord_sequence(
    chord_notes,
    bpm,
    dest_folder=None
):
    """
    Export a chord (.mid) from the given notes and tempo.

    Args:
      chord_notes  (list[int]):       MIDI note numbers for the chord
      bpm          (int):             Tempo in beats per minute
      dest_folder  (str, optional):   Directory to save file; uses export_folder if omitted
    """
    folder = dest_folder or export_folder
    if not folder or not chord_notes:
        return

    mid = MidiFile(type=0, ticks_per_beat=960)
    track = MidiTrack()
    mid.tracks.append(track)

    # tempo
    track.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=0))

    # all notes on at t=0
    for n in chord_notes:
        track.append(Message('note_on', note=n-12, velocity=100, time=0))

    # all notes off after 4 quarter notes
    release = 4 * mid.ticks_per_beat
    # send first note-off with delay, others immediately
    track.append(Message('note_off', note=chord_notes[0], velocity=0, time=release))
    for n in chord_notes[1:]:
        track.append(Message('note_off', note=n, velocity=0, time=0))

    # filename
    date_str = datetime.datetime.now().strftime("%Y%b%d")
    counter = 1
    while True:
        fn = f"{date_str}_CHORD_{counter:03d}.mid"
        path = os.path.join(folder, fn)
        if not os.path.exists(path):
            break
        counter += 1

    mid.save(path)
