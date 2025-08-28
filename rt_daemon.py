# rt_daemon.py
import os, sys, time, json, socket, subprocess, atexit, stat

CTRL_SOCK = "/tmp/gord_rt.sock"

def _executable_bit(path):
    try:
        return bool(os.stat(path).st_mode & stat.S_IXUSR)
    except Exception:
        return False

def find_gordrt():
    """
    Search order:
      1) tools/GordRT (dev checkout)
      2) PyInstaller bundle (sys._MEIPASS)
      3) .app Resources (…/YourApp.app/Contents/Resources/GordRT)
      4) CWD fallback
    """
    here = os.path.dirname(os.path.abspath(__file__))

    cand = os.path.join(here, "tools", "GordRT")
    if os.path.exists(cand) and _executable_bit(cand): return cand

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = os.path.join(meipass, "GordRT")
        if os.path.exists(cand): return cand

    exe = sys.executable
    if ".app/Contents/MacOS" in exe:
        resources = exe.split("/Contents/MacOS")[0] + "/Contents/Resources"
        cand = os.path.join(resources, "GordRT")
        if os.path.exists(cand): return cand

    return os.path.join(here, "GordRT")

class GordRTDaemon:
    def __init__(self, dest: str = ""):
        self.dest = dest or os.environ.get("GORD_MIDI_DEST", "")
        self.proc = None

    def _socket_ready(self, timeout=3.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if os.path.exists(CTRL_SOCK):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                    s.sendto(b'{"cmd":"noop"}', CTRL_SOCK)
                    s.close()
                    return True
                except OSError:
                    pass
            time.sleep(0.05)
        return False

    def ensure_running(self):
        # Always relaunch to pick up fresh env/ports
        if self._socket_ready(timeout=0.1):
            self.stop()
            time.sleep(0.05)

        exe = find_gordrt()
        if not os.path.exists(exe):
            raise FileNotFoundError(f"GordRT not found at: {exe}")

        try: os.unlink(CTRL_SOCK)
        except FileNotFoundError: pass

        env = os.environ.copy()


        dest = os.environ.get("GORD_MIDI_DEST", "")
        src  = os.environ.get("GORD_MIDI_SRC", "")

        # speak the daemon’s actual env contract; no virtual port gets created
        env["GORD_MIDI_OUT"] = dest      # "IAC Driver gord out"
        env["GORD_MIDI_IN"]  = src       # "IAC Driver gord in"
        env["GORD_CLOCK_IN"] = src



        # External clock ON so daemon follows incoming START/CLOCK
        env["GORD_EXTERNAL_CLK"] = "1" if os.environ.get("GORD_EXTERNAL_CLK") else ""

        subprocess.run(["pkill","-x","GordRT"], check=False)
        self.proc = subprocess.Popen([exe], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.proc = subprocess.Popen(
            [exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )

        if not self._socket_ready(timeout=3.0):
            raise RuntimeError("GordRT failed to start (socket not ready).")

        atexit.register(self.stop)

    def stop(self):
        # Ask daemon to stop, then tear down process/socket
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            for cmd in ("stop", "panic"):
                s.sendto(json.dumps({"cmd": cmd}).encode("utf-8"), CTRL_SOCK)
            s.close()
        except OSError:
            pass

        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                for _ in range(20):
                    if self.proc.poll() is not None: break
                    time.sleep(0.05)
                if self.proc.poll() is None:
                    self.proc.kill()
            except Exception:
                pass
        self.proc = None

        try: os.unlink(CTRL_SOCK)
        except FileNotFoundError: pass
