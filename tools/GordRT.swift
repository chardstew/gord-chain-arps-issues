import Foundation
import CoreMIDI
import CoreAudio
import Darwin

// ────────────────────────── Utilities ──────────────────────────
@inline(__always) func nanosToHost(_ ns: UInt64) -> UInt64 { AudioConvertNanosToHostTime(ns) }
@inline(__always) func hostNow() -> UInt64 { AudioGetCurrentHostTime() }

// Messages (JSON over /tmp/gord_rt.sock)
enum Cmd: String, Codable { case set, seq, start, stop, panic, chain }
struct MsgSet: Codable {
    let cmd: Cmd
    let tempo: Double?
    let subdivision: Int?
    let gate: Double?
    let channel: Int?
    let transpose: Int?
    /// If true, apply on *next* step without debounce
    let immediate: Bool?
    /// NEW: follow external MIDI clock/transport when true
    let slave_mode: Bool?
}
struct MsgSeq: Codable { let cmd: Cmd; let notes: [Int] } // -1 = rest
// Add below MsgSeq
struct ChainSlot: Codable { let notes: [Int]; let loops: Int }
struct MsgChain: Codable { let cmd: Cmd; let slots: [ChainSlot]; let index: Int? }


@inline(__always) func midichannel(_ ch:Int) -> UInt8 { UInt8((ch-1) & 0x0F) }
@inline(__always) func stOn(_ ch:Int)->UInt8  { 0x90 | midichannel(ch) }
@inline(__always) func stOff(_ ch:Int)->UInt8 { 0x80 | midichannel(ch) }

// ────────────────────────── Shared state ──────────────────────────
final class Shared {
    // current “effective” musical state
    var running: Bool = false
    var bpm: Double = 120.0
    var subdiv: Int = 4         // 1=whole,2=half,4=quarter,8=eighth...
    var gatePct: Double = 50.0  // 0..100
    var channel: Int = 1        // 1..16
    var transpose: Int = 0
    var notes: [Int] = [-1] // start silent; -1 = rest
    // --- note scheduling fences ---
    var lastOffTS: UInt64 = 0   // host time of the most recent scheduled Note-Off
    var minOnTS:  UInt64 = 0    // do not schedule any Note-On earlier than this



    // Add near other state vars
    var chainSlots: [ChainSlot] = []  // empty => chain disabled
    var chainIndex: Int = 0           // which slot is active
    var loopsLeft: Int = 0            // loops remaining in the current slot


    // pending (quantized) changes
    var pendingSet: MsgSet? = nil
    var applyParamsAfter: UInt64? = nil
    var pendingNotes: [Int]? = nil

    // scheduler state (host time)
    var nextStepHost: UInt64? = nil
    var stepIndex: Int = -1

    // policy
    let paramDebounceNs: UInt64 = 20_000_000
    let quantizeSeqToBar: Bool = true

    // ── External clock (slave) ──
    var extSlave: Bool = false
    var tickCounter: Int = 0           // counts F8 clocks
    var lastClockTS: UInt64 = 0        // host ticks timestamp of last F8
    var clockAvg: Double = 0           // EMA of F8 delta in host ticks

    let lock = NSLock()
}

// ────────────────────────── CoreMIDI IO ──────────────────────────
struct MidiIO {
    let client: MIDIClientRef
    let outPort: MIDIPortRef
    let inPort: MIDIPortRef?
    let dest: MIDIEndpointRef
}

func getName(_ obj: MIDIObjectRef) -> String {
    var cf: Unmanaged<CFString>?
    if MIDIObjectGetStringProperty(obj, kMIDIPropertyName, &cf) == noErr,
       let s = cf?.takeRetainedValue() as String? { return s }
    return ""
}

func openMidiOut() -> (client: MIDIClientRef, outPort: MIDIPortRef, dest: MIDIEndpointRef) {
    var client = MIDIClientRef()
    guard MIDIClientCreate("GordRT" as CFString, nil, nil, &client) == noErr else {
        fatalError("MIDIClientCreate failed")
    }

    var out = MIDIPortRef()
    guard MIDIOutputPortCreate(client, "GordRT-Out" as CFString, &out) == noErr else {
        fatalError("MIDIOutputPortCreate failed")
    }

    // Require explicit destination; no virtual source fallback.
    let needle = (ProcessInfo.processInfo.environment["GORD_MIDI_DEST"] ?? "").lowercased()
    guard !needle.isEmpty else { fatalError("Set GORD_MIDI_DEST to your output destination (e.g. 'gord out').") }

    let n = MIDIGetNumberOfDestinations()
    var pick: MIDIEndpointRef = 0
    for i in 0..<n {
        let d = MIDIGetDestination(i)
        if d != 0, getName(d).lowercased().contains(needle) { pick = d; break }
    }
    guard pick != 0 else { fatalError("Destination not found for GORD_MIDI_DEST=\(needle)") }
    fputs("[GordRT] sending to: \(getName(pick))\n", stderr)

    return (client, out, pick)
}


func sendPacket(ts: MIDITimeStamp, bytes: [UInt8], io: MidiIO) {
    // Minimal duplicate-NoteOn detector (logs only on suspicious re-triggers)
    if bytes.count >= 3, (bytes[0] & 0xF0) == 0x90, bytes[2] > 0 {
        struct Last { static var lastOn: [UInt8: MIDITimeStamp] = [:] }
        let n = bytes[1]
        let prev = Last.lastOn[n] ?? 0
        Last.lastOn[n] = ts
        if prev != 0 {
            let dtTicks = ts &- prev
            // ~25ms window (adjust as needed):
            let thresh = AudioConvertNanosToHostTime(25_000_000)
            if dtTicks < thresh {
                fputs("[GordRT] DUP NoteOn n=\(n) dt=\(dtTicks)ticks (~<25ms)\n", stderr)
            }
        }
    }
    var list = MIDIPacketList(numPackets: 1, packet: MIDIPacket())
    withUnsafeMutablePointer(to: &list) { pl in
        let pkt = MIDIPacketListInit(pl)
        var local = bytes
        local.withUnsafeMutableBufferPointer { bp in
            _ = MIDIPacketListAdd(pl, 1024, pkt, ts, bp.count, bp.baseAddress!)
        }
    }
    var listCopy = list
    withUnsafePointer(to: &listCopy) { p in MIDISend(io.outPort, io.dest, p) }
}

// ────────────────────────── MIDI In (clock/transport) ──────────────────────────
final class RTContext {
    let shared: Shared
    let io: MidiIO
    init(shared: Shared, io: MidiIO) { self.shared = shared; self.io = io }
}

func forEachPacket(in list: UnsafePointer<MIDIPacketList>, _ f: (MIDIPacket)->Void) {
    var pkt = list.pointee.packet
    for _ in 0..<list.pointee.numPackets {
        f(pkt)
        pkt = withUnsafePointer(to: &pkt) { p in MIDIPacketNext(p).pointee }
    }
}

func handlePacket(_ packet: MIDIPacket, ctx: RTContext) {
    let ts = packet.timeStamp
    var data = packet.data
    withUnsafeBytes(of: &data) { raw in
        let base = raw.baseAddress!.assumingMemoryBound(to: UInt8.self)
        let len  = Int(packet.length)
        for i in 0..<len {
            let b = base[i]
            switch b {
            case 0xFA: // Start (fence against lingering OFF)
                let safe = nanosToHost(1_000_000) // ~1ms
                ctx.shared.lock.lock()
                let lastOff = ctx.shared.lastOffTS
                ctx.shared.running      = true
                ctx.shared.tickCounter  = 0
                ctx.shared.stepIndex    = -1
                ctx.shared.lastClockTS  = ts
                ctx.shared.minOnTS      = lastOff &+ safe   // block next ON until after prior OFF
                // DO NOT clear lastOffTS here
                ctx.shared.pendingNotes = nil
                ctx.shared.pendingSet   = nil
                ctx.shared.applyParamsAfter = nil
                ctx.shared.lock.unlock()

            case 0xFB: // Continue
                ctx.shared.lock.lock()
                ctx.shared.running = true
                ctx.shared.lock.unlock()

            case 0xFC: // Stop (keep lastOffTS so next Start can fence)
                ctx.shared.lock.lock()
                ctx.shared.running      = false
                ctx.shared.stepIndex    = -1
                ctx.shared.nextStepHost = nil
                ctx.shared.tickCounter  = 0
                ctx.shared.minOnTS      = 0
                // DO NOT clear lastOffTS
                ctx.shared.pendingNotes = nil
                ctx.shared.pendingSet   = nil
                ctx.shared.applyParamsAfter = nil
                ctx.shared.lock.unlock()

            case 0xF8: // Clock (24 PPQN)
                ctx.shared.lock.lock()

                // No auto-start on clocks.
                let follow = ctx.shared.extSlave && ctx.shared.running && !ctx.shared.notes.isEmpty

                // tick timing EMA
                let prevTS = ctx.shared.lastClockTS
                if prevTS != 0 {
                    let dt = ts &- prevTS
                    let a = 0.2
                    ctx.shared.clockAvg = (1.0 - a) * ctx.shared.clockAvg + a * Double(dt)
                }
                ctx.shared.lastClockTS = ts

                if follow {
                    let subdiv = max(1, ctx.shared.subdiv)
                    let tps = max(1, 96 / subdiv) // ticks-per-step at 24 PPQN
                    ctx.shared.tickCounter += 1

                    if ctx.shared.tickCounter >= tps {
                        ctx.shared.tickCounter = 0

                        // Fence: don't let a new ON start before the last OFF from old grid
                        let fence = ctx.shared.minOnTS
                        if fence > 0 && ts <= fence {
                            // skip this boundary; try again on next one
                        } else {
                            // SWAP BEFORE ADVANCING INDEX
                            if let newSeq = ctx.shared.pendingNotes {
                                ctx.shared.notes = newSeq
                                ctx.shared.pendingNotes = nil
                                ctx.shared.stepIndex = -1
                            }

                            var idx = ctx.shared.stepIndex + 1
                            ctx.shared.stepIndex = idx

                            let notes = ctx.shared.notes
                            let curLen = max(1, notes.count)
                            let rawN = notes[idx % curLen]
                            let ch  = ctx.shared.channel
                            let tr  = ctx.shared.transpose

                            let gatePct = min(100.0, max(0.0, ctx.shared.gatePct))
                            let gateClocksRaw = Int(round(Double(tps) * gatePct / 100.0))
                            let gateClocks = max(1, min(tps - 1, gateClocksRaw))
                            let avg = ctx.shared.clockAvg
                            let gateHost: UInt64 = (avg > 1.0)
                                ? UInt64(Double(gateClocks) * avg)
                                : nanosToHost(10_000_000) // ~10ms fallback

                            if rawN >= 0 && rawN <= 127 {
                                let nn = UInt8(min(127, max(0, rawN + tr)))
                                // schedule ON now (fence cleared)
                                sendPacket(ts: ts,             bytes: [stOn(ch),  nn, 100], io: ctx.io)
                                // schedule OFF and remember it for future fences
                                let offTS = ts &+ gateHost
                                sendPacket(ts: offTS,          bytes: [stOff(ch), nn,   0], io: ctx.io)
                                ctx.shared.lastOffTS = offTS
                                ctx.shared.minOnTS   = 0  // fence consumed
                            }

                            // bar-end advance (slave path)
                            let isBarEnd = ((idx + 1) % curLen) == 0
                            if isBarEnd {
                                if !ctx.shared.chainSlots.isEmpty {
                                    if ctx.shared.loopsLeft != Int.max && ctx.shared.loopsLeft > 0 {
                                        ctx.shared.loopsLeft -= 1
                                    }
                                    if ctx.shared.loopsLeft == 0 {
                                        ctx.shared.chainIndex = (ctx.shared.chainIndex + 1) % ctx.shared.chainSlots.count
                                        let next = ctx.shared.chainSlots[ctx.shared.chainIndex]
                                        ctx.shared.notes = next.notes
                                        ctx.shared.loopsLeft = (next.loops <= 0) ? Int.max : max(1, next.loops)
                                        ctx.shared.stepIndex = -1
                                    }
                                }
                            }
                        }
                    }
                }

                ctx.shared.lock.unlock()

            default:
                break
            }
        }
    }
}


let midiRead: MIDIReadProc = { list, refCon, _ in
    guard let refCon = refCon else { return }
    let ctx = Unmanaged<RTContext>.fromOpaque(refCon).takeUnretainedValue()
    ctx.shared.lock.lock()
    let slave = ctx.shared.extSlave
    ctx.shared.lock.unlock()
    if !slave { return } // ignore clocks when not slaved
    forEachPacket(in: list) { pkt in handlePacket(pkt, ctx: ctx) }
}

func setupMidiClockIn(client: MIDIClientRef, ctx: RTContext) -> MIDIPortRef? {
    var inPort = MIDIPortRef()
    guard MIDIInputPortCreate(client, "GordRT-In" as CFString, midiRead,
                              Unmanaged.passUnretained(ctx).toOpaque(), &inPort) == noErr else {
        fputs("[GordRT] MIDIInputPortCreate failed\n", stderr)
        return nil
    }

    let needle = (ProcessInfo.processInfo.environment["GORD_MIDI_SRC"] ?? "").lowercased()
    guard !needle.isEmpty else {
        fputs("[GordRT] no clock source (set GORD_MIDI_SRC if using slave mode)\n", stderr)
        return inPort
    }

    let nsrc = MIDIGetNumberOfSources()
    var pick: MIDIEndpointRef = 0
    for i in 0..<nsrc {
        let s = MIDIGetSource(i)
        if s != 0, getName(s).lowercased().contains(needle) { pick = s; break }
    }
    if pick != 0 {
        MIDIPortConnectSource(inPort, pick, nil)
        fputs("[GordRT] clock source: \(getName(pick))\n", stderr)
    } else {
        fputs("[GordRT] WARNING: GORD_MIDI_SRC not found; slave mode will not advance\n", stderr)
    }
    return inPort
}

// ────────────────────────── IPC (JSON over UNIX DGRAM) ──────────────────────────
func runIPC(shared: Shared, sockPath: String) {
    unlink(sockPath)
    let fd = socket(AF_UNIX, SOCK_DGRAM, 0)
    guard fd >= 0 else { perror("socket"); exit(1) }

    var addr = sockaddr_un()
    memset(&addr, 0, MemoryLayout<sockaddr_un>.size)
    addr.sun_family = sa_family_t(AF_UNIX)
    let maxPath = MemoryLayout.size(ofValue: addr.sun_path)
    _ = sockPath.withCString { cs in
        withUnsafeMutablePointer(to: &addr.sun_path) { sp in
            sp.withMemoryRebound(to: CChar.self, capacity: maxPath) { dst in
                strncpy(dst, cs, maxPath - 1)
            }
        }
    }
    addr.sun_len = UInt8(
        MemoryLayout.offset(of: \sockaddr_un.sun_path)! +
        min(maxPath, sockPath.utf8.count + 1)
    )
    let slen = socklen_t(addr.sun_len)

    let ok = withUnsafePointer(to: &addr) { p in
        p.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, slen) == 0 }
    }
    guard ok else { perror("bind"); exit(1) }

    let dec = JSONDecoder()
    var buf = [UInt8](repeating: 0, count: 4096)
    fputs("[GordRT] control socket: \(sockPath)\n", stderr)

    while true {
        let n = recv(fd, &buf, buf.count, 0)
        if n <= 0 { continue }
        let data = Data(bytes: buf, count: n)

        // panic
        if let first = try? dec.decode([String:String].self, from: data),
           first["cmd"] == "panic" {
            shared.lock.lock()
            shared.running = false
            shared.nextStepHost = nil
            shared.pendingSet = nil
            shared.applyParamsAfter = nil
            shared.pendingNotes = nil
            shared.notes = [-1]
            shared.stepIndex = -1
            shared.tickCounter = 0
            shared.lock.unlock()
            continue
        }

    // chain: install slots and make chain own playback (clean handoff + fence)
    if let c = try? dec.decode(MsgChain.self, from: data), c.cmd == .chain {
        let lead  = nanosToHost(5_000_000)  // ~5ms headroom
        let safe  = nanosToHost(1_000_000)  // ~1ms OFF→ON fence
        let now   = hostNow()

        shared.lock.lock()
        shared.chainSlots = c.slots
        let hasSlots = !shared.chainSlots.isEmpty
        shared.chainIndex = hasSlots ? max(0, min((c.index ?? 0), shared.chainSlots.count - 1)) : 0

        // kill any leftovers so we have a single source of truth
        shared.pendingNotes = nil
        shared.pendingSet   = nil

        if hasSlots {
            let slot = shared.chainSlots[shared.chainIndex]
            shared.notes      = slot.notes
            shared.loopsLeft  = (slot.loops <= 0) ? Int.max : max(1, slot.loops)
            shared.stepIndex  = -1

            // ⬅️ NEW: if slaved, also reset tickCounter so first boundary is clean
            if shared.extSlave { shared.tickCounter = 0 }

            // Fence the first new ON after the last OFF (and give scheduler a target)
            let startAt = max(now &+ lead, shared.lastOffTS &+ safe)
            shared.nextStepHost = startAt
            shared.minOnTS      = startAt
        } else {
            shared.notes      = [-1]
            shared.loopsLeft  = 0
            shared.stepIndex  = -1
        }
        shared.lock.unlock()
        continue
    }


        // set (debounced) + immediate slave_mode
        if let m = try? dec.decode(MsgSet.self, from: data), m.cmd == .set {
            shared.lock.lock()
            if let sm = m.slave_mode { shared.extSlave = sm }
            shared.pendingSet = m
            let wait = (m.immediate ?? false) ? 0 : shared.paramDebounceNs
            shared.applyParamsAfter = hostNow() + nanosToHost(wait)
            shared.lock.unlock()
            continue
        }

        // seq: ignore while CHAIN is active; otherwise normal behavior
        if let s = try? dec.decode(MsgSeq.self, from: data), s.cmd == .seq {
            shared.lock.lock()
            if !shared.chainSlots.isEmpty {
                shared.lock.unlock()
                continue
            }
            let newNotes = s.notes
            let currentlySilent = shared.notes.isEmpty || !shared.notes.contains(where: { $0 >= 0 })
            if !shared.running || currentlySilent {
                shared.notes        = newNotes
                shared.stepIndex    = -1
                shared.nextStepHost = nil
                shared.pendingNotes = nil
            } else {
                shared.pendingNotes = newNotes
            }
            shared.lock.unlock()
            continue
        }

        // start (fenced to avoid overlap with last OFF)
        if let t = try? dec.decode([String:String].self, from: data), t["cmd"] == "start" {
            let lead  = nanosToHost(5_000_000)    // ~5ms headroom
            let safe  = nanosToHost(1_000_000)    // ~1ms OFF→ON fence
            let now   = hostNow()
            shared.lock.lock()
            let lastOff = shared.lastOffTS
            let startAt = max(now &+ lead, lastOff &+ safe)

            shared.running        = true
            shared.stepIndex      = -1
            shared.nextStepHost   = startAt   // non-slave scheduler honors this
            shared.tickCounter    = 0
            shared.minOnTS        = startAt   // ensure first ON can’t predate last OFF
            // DO NOT zero lastOffTS here (we want the fence)
            shared.pendingNotes   = nil
            shared.pendingSet     = nil
            shared.applyParamsAfter = nil
            shared.lock.unlock()
            continue
        }

        // stop (preserve lastOffTS so next start can fence against it)
        if let t = try? dec.decode([String:String].self, from: data), t["cmd"] == "stop" {
            shared.lock.lock()
            shared.running        = false
            shared.stepIndex      = -1
            shared.nextStepHost   = nil
            shared.tickCounter    = 0
            shared.minOnTS        = 0
            // DO NOT zero lastOffTS here
            shared.pendingNotes   = nil
            shared.pendingSet     = nil
            shared.applyParamsAfter = nil
            shared.lock.unlock()
            continue
        }
    }
}

// ────────────────────────── Scheduler (internal master) ──────────────────────────
func runScheduler(shared: Shared, io: MidiIO) {
    // tighter for live play
    let LOOKAHEAD_NS: UInt64 = 30_000_000   // 30 ms
    let LEAD_NS: UInt64      =  5_000_000   // 5 ms
    let LEAD_TICKS           = nanosToHost(LEAD_NS)

    while true {
        // snapshot state
        shared.lock.lock()
        let running   = shared.running
        var bpm       = shared.bpm
        var subdiv    = shared.subdiv
        var gatePct   = shared.gatePct
        var channel   = shared.channel
        var transpose = shared.transpose
        var notes     = shared.notes
        var nextHost  = shared.nextStepHost
        var idx       = shared.stepIndex
        let pending   = shared.pendingSet
        let applyAfter = shared.applyParamsAfter
        let extSlave  = shared.extSlave
        shared.lock.unlock()


        // commit debounced params (applies even when slaved)
        if let ap = applyAfter, hostNow() >= ap, let p = pending {
            var tempoChanged  = false
            var subdivChanged = false

            // detect changes
            if let t = p.tempo       { let new = max(1.0, t); tempoChanged  = (new != bpm);    bpm = new }
            if let s = p.subdivision { let new = max(1,   s); subdivChanged = (new != subdiv); subdiv = new }
            if let g = p.gate        { gatePct   = max(0.0, min(100.0, g)) }
            if let c = p.channel     { channel   = min(16, max(1, c)) }
            if let tr = p.transpose  { transpose = tr }

            // commit to shared and capture what we need
            shared.lock.lock()
            shared.pendingSet       = nil
            shared.applyParamsAfter = nil
            shared.bpm       = bpm
            shared.subdiv    = subdiv
            shared.gatePct   = gatePct
            shared.channel   = channel
            shared.transpose = transpose
            let lastOff  = shared.lastOffTS
            let isSlave  = shared.extSlave
            shared.lock.unlock()

            let wasRunning = running

            // SUBDIV change: fence + re-prime (slave vs non-slave paths)
            if subdivChanged && wasRunning {
                let safety = nanosToHost(1_000_000) // 1ms cushion
                let fence  = lastOff &+ safety
                if isSlave {
                    shared.lock.lock()
                    shared.stepIndex   = -1
                    shared.tickCounter = 0
                    shared.minOnTS     = fence   // block Note-Ons until last OFF clears
                    shared.lock.unlock()
                } else {
                    let lead    = nanosToHost(5_000_000) // 5ms lookahead
                    let startAt = max(hostNow() &+ lead, fence)
                    shared.lock.lock()
                    shared.stepIndex    = -1
                    shared.nextStepHost = startAt
                    shared.minOnTS      = startAt
                    shared.lock.unlock()
                }
            }
            // TEMPO change: no restart; only ensure next event isn't in the past (non-slave)
            else if tempoChanged && wasRunning && !isSlave {
                shared.lock.lock()
                if let nh = shared.nextStepHost, nh < hostNow() &+ nanosToHost(1_000_000) {
                    shared.nextStepHost = hostNow() &+ nanosToHost(5_000_000)
                }
                shared.lock.unlock()
            }
        }


        // slave: external F8 drives stepping
        if extSlave {
            Thread.sleep(forTimeInterval: 0.005)
            continue
        }

        if running && !notes.isEmpty {
            // compute timing
            let step_ns_d = (60.0 / bpm) * (4.0 / Double(max(1, subdiv))) * 1_000_000_000.0
            let stepTicks = nanosToHost(UInt64(step_ns_d))
            var gate_ns = UInt64(step_ns_d * (gatePct / 100.0))
            if gate_ns <= 1_000_000 { gate_ns = 1_000_000 }
            if gate_ns >= UInt64(step_ns_d) - 1_000_000 { gate_ns = UInt64(step_ns_d) - 1_000_000 }
            let gateTicks = nanosToHost(gate_ns)

            if nextHost == nil { nextHost = hostNow() + LEAD_TICKS }
            let horizon = hostNow() + nanosToHost(LOOKAHEAD_NS)

            while let nh = nextHost, nh <= horizon {
                // SWAP BEFORE ADVANCING INDEX
                shared.lock.lock()
                if let newSeq = shared.pendingNotes {
                    shared.notes = newSeq
                    shared.pendingNotes = nil
                    shared.stepIndex = -1
                    notes = newSeq
                    idx = -1
                }
                shared.lock.unlock()

                idx += 1
                let curLen = max(1, notes.count)
                let raw = notes[idx % curLen]
                if raw >= 0 && raw <= 127 {
                    let nn = UInt8(min(127, max(0, raw + transpose)))
                    sendPacket(ts: nh,             bytes: [stOn(channel),  nn, 100], io: io)
                    let offTS = nh + gateTicks
                    sendPacket(ts: offTS, bytes: [stOff(channel), nn, 0], io: io)
                    shared.lock.lock()
                    if offTS > shared.lastOffTS { shared.lastOffTS = offTS }
                    shared.lock.unlock()

                }
                let isBarEnd = ((idx + 1) % curLen) == 0
                if isBarEnd {
                    shared.lock.lock()
                    if !shared.chainSlots.isEmpty {
                        if shared.loopsLeft != Int.max && shared.loopsLeft > 0 { shared.loopsLeft -= 1 }
                        if shared.loopsLeft == 0 {
                            shared.chainIndex = (shared.chainIndex + 1) % shared.chainSlots.count
                            let next = shared.chainSlots[shared.chainIndex]
                            shared.notes = next.notes
                            shared.loopsLeft = (next.loops <= 0) ? Int.max : max(1, next.loops)
                            shared.stepIndex = -1
                            // keep locals in sync
                            notes = next.notes
                            idx = -1
                        }
                    }
                    shared.lock.unlock()
                }



                nextHost = nh + stepTicks
                break  // schedule one step only; allow immediate swaps next pass
            }

            shared.lock.lock()
            shared.nextStepHost = nextHost
            shared.stepIndex    = idx
            shared.lock.unlock()
            Thread.sleep(forTimeInterval: 0.005)
        } else {
            Thread.sleep(forTimeInterval: 0.01)
        }
    }
}

// ────────────────────────── Main ──────────────────────────
@main
struct Main {
    static func main() {
        let (client, outPort, dest) = openMidiOut()
        let shared = Shared()
        // Build IO (inPort inserted after we have the read context)
        var io = MidiIO(client: client, outPort: outPort, inPort: nil, dest: dest)
        let ctx = RTContext(shared: shared, io: io)
        let inPort = setupMidiClockIn(client: client, ctx: ctx)
        io = MidiIO(client: client, outPort: outPort, inPort: inPort, dest: dest)

        // control socket for Python client
        let sockPath = "/tmp/gord_rt.sock"
        DispatchQueue.global(qos: .userInteractive).async {
            runIPC(shared: shared, sockPath: sockPath)
        }
        fputs("[GordRT] scheduler up. Use \(sockPath) for control.\n", stderr)
        runScheduler(shared: shared, io: io)
    }
}
