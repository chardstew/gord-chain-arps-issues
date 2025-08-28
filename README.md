Gord (Python/macOS) — Quick Setup for Logic

1) Install Python deps
python3 -m pip install mido python-rtmidi pillow

If you get a “tkinter” import error:
brew install python-tk

2) Create IAC ports (virtual MIDI)
Open Audio MIDI Setup → Window ▸ Show MIDI Studio.
Double-click IAC Driver.
Check “Device is online.”
Add two ports and name them exactly:
gord in
gord out
Click Apply and close the window.

3) Logic setup
Enable IAC inputs:
Logic Pro ▸ Settings ▸ MIDI ▸ Inputs → check the IAC ports (you should see IAC Driver gord out).

Send MIDI Clock to Gord if you want Logic to be the clock:
File ▸ Project Settings ▸ Synchronization ▸ MIDI
Transmit MIDI Clock → choose IAC Driver “gord in”
Enable Start/Stop

Note:
'gord out' is INPUT for Logic (from Gord).
'gord in' OUTPUTS sync to Gord from Logic (for slave mode).

Avoid feedback: don’t also route Logic’s MIDI output back to gord out unless you know why.

4) Create a track: Add a Software Instrument track, load any synth, and arm the track (R).

5) Launch Gord