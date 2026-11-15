#!/usr/bin/env python3
"""Native Linux flasher for the 8BitDo N64 Modkit — protocol confirmed from a
USB capture of the official v1.04 update.

Modes/devices:
  DInput runtime  2dc8:2869   (send jump-to-boot here)
  Bootloader      2dc8:5750   (do the flash here; ep2 OUT / ep1 IN, 64B interrupt)

Flash sequence on the bootloader (ebitdo-style framing):
  GET_VERIFICATION_ID(0x1a) -> 36-byte verification id
  FW_UPDATE_HEADER(sub 0x16, cmd 0x01, 28-byte .dat header) -> ACK
  prepare(0x1d) -> ACK
  FW_UPDATE_DATA(sub 0x16, cmd 0x00, 32 ENCRYPTED bytes) x N -> ACK each
  FW_SET_ENCODE_ID(sub 0x16, cmd 0x06, 12 bytes)
  FW_GET_VERSION(sub 0x16, cmd 0x04) -> version
  FW_UPDATE_OK(sub 0x16, cmd 0x02)

The firmware DATA is the ENCRYPTED .dat payload (dat[28:]); the device decrypts internally.
The ENCODE_ID is computed from the unit's verification id (see encode_id()), so any unit can
be flashed.

Requires pyusb + libusb; run as root or with the 2dc8/0483 udev rule installed.
Usage:
  flasher.py info
  flasher.py jump-boot
  flasher.py flash build/n64modkit.dat [--verif-id HEX]
  flasher.py encode-id HEX          # print the encode-id for a verification id
"""
import argparse, struct, sys, time

VID = 0x2DC8
PID_RUNTIME = 0x2869
PID_BOOT    = 0x5750
EP_OUT = 0x02
EP_IN  = 0x81
TIMEOUT = 5000
CHUNK = 32
HDR = 28

VERIF_LEN = 36

# Encode-id key table: fwupd's 8BitDo plugin, plugins/ebitdo/fu-ebitdo-device.c
# (app_key_index; fwupd is LGPL-2.1-or-later, Copyright 2016 Richard Hughes).
ENCODE_KEYS = (
    0x186976e5, 0xcac67acd, 0x38f27fee, 0x0a4948f1, 0xb75b7753, 0x1f8ffa5c, 0xbff8cf43, 0xc4936167,
    0x92bd03f0, 0x5573c6ed, 0x57d8845b, 0x827197ac, 0xb91901c9, 0x3917edfe, 0xbcd6344f, 0xcf9e23b5,
)


def encode_id(verif_id):
    """12-byte FW_SET_ENCODE_ID payload from the 36-byte verification id: each of the first
    three little-endian words w becomes w ^ ENCODE_KEYS[w & 0xF] (as fwupd and 8BitDo's own
    updater do; checked against a capture of the official updater). Only those 12 bytes are
    used, which come from the chip, so it doesn't matter whether the app area is erased."""
    words = struct.unpack_from("<3I", verif_id)
    return struct.pack("<3I", *(w ^ ENCODE_KEYS[w & 0xF] for w in words))

# subtypes / cmds
SUB_GET_VERIF = 0x1a
SUB_PREPARE   = 0x1d
SUB_FLASH     = 0x16     # UPDATE_FIRMWARE_DATA category
CMD_DATA=0x00; CMD_HEADER=0x01; CMD_OK=0x02; CMD_GETVER=0x04; CMD_ENCODE=0x06; CMD_ACK=0x14
JUMP_BOOT = 0x50         # sent to runtime to enter bootloader


def frame(subtype, cmd, payload=b"", size=64):
    buf = bytearray(size)
    buf[1] = 0x00  # type = USER_CMD
    buf[2] = subtype
    if payload:
        struct.pack_into("<H", buf, 3, len(payload) + 3)   # cmd_len
        buf[5] = cmd
        struct.pack_into("<H", buf, 6, len(payload))        # payload_len
        buf[8:8+len(payload)] = payload
        buf[0] = len(payload) + 7                            # pkt_len
    else:
        struct.pack_into("<H", buf, 3, 1)
        buf[5] = cmd
        buf[0] = 5
    return bytes(buf)


def open_dev(pid):
    import usb.core, usb.util
    dev = usb.core.find(idVendor=VID, idProduct=pid)
    if dev is None:
        return None
    for cfg in dev:
        for intf in cfg:
            n = intf.bInterfaceNumber
            try:
                if dev.is_kernel_driver_active(n):
                    dev.detach_kernel_driver(n)
            except Exception:
                pass
    # Only configure an unconfigured device. Re-sending SET_CONFIGURATION to a configured one
    # makes Linux reset its endpoint data toggles while the bootloader's USB stack keeps its
    # own, so the next packet in each direction is silently dropped as a "duplicate". After
    # that has happened, `reset` (a USB port reset) puts both sides back to DATA0.
    try:
        dev.get_active_configuration()
    except usb.core.USBError:
        dev.set_configuration()
    return dev


def do_reset():
    """USB port reset of the modkit (bootloader or runtime), then wait for it to re-enumerate."""
    import usb.core
    for pid in (PID_BOOT, PID_RUNTIME):
        dev = usb.core.find(idVendor=VID, idProduct=pid)
        if dev is not None:
            break
    else:
        sys.exit("no modkit found")
    print(f"resetting {VID:04x}:{pid:04x} ...")
    try:
        dev.reset()
    except usb.core.USBError as e:
        print("  reset:", e)
    t0 = time.time()
    while time.time() - t0 < 10:
        time.sleep(0.25)
        for p in (PID_BOOT, PID_RUNTIME):
            if usb.core.find(idVendor=VID, idProduct=p) is not None:
                print(f"present as {VID:04x}:{p:04x} after {time.time()-t0:.1f}s")
                return
    sys.exit("device did not come back within 10 s")


def send(dev, data):
    dev.write(EP_OUT, data, TIMEOUT)

def recv(dev, n=64):
    return bytes(dev.read(EP_IN, n, TIMEOUT))

def expect_ack(dev, what, timeout=TIMEOUT):
    r = bytes(dev.read(EP_IN, 64, timeout))
    if len(r) < 6 or r[5] != CMD_ACK:
        raise SystemExit(f"no ACK for {what}: {r[:8].hex()}")

def drain(dev):
    """Discard replies left over from an earlier, interrupted session."""
    import usb.core
    n = 0
    while True:
        try:
            dev.read(EP_IN, 64, 100); n += 1
        except usb.core.USBTimeoutError:
            return n

def recv_reply(dev, pos, val, what, tries=4):
    """Next reply with r[pos] == val, skipping stray ACKs. Replies seen in the capture:
    verification id 2d 00 19 24 00 <36-byte id> (r[2] = 0x19, length 0x24 at r[3:5]);
    version 0c 00 16 07 00 04 04 00 68 00 (r[5] = 0x04, version LE at r[8:10]);
    ACK 06 00 16 01 00 14 (r[5] = 0x14)."""
    for _ in range(tries):
        r = recv(dev)
        if len(r) > pos and r[pos] == val:
            return r
        print(f"  (skipping {r[:8].hex()} while waiting for {what})")
    raise SystemExit(f"no reply for {what}")


def do_jump_boot():
    dev = open_dev(PID_RUNTIME)
    if dev is None:
        sys.exit(f"runtime device {VID:04x}:{PID_RUNTIME:04x} not found "
                 "(put modkit in D-input mode and plug in)")
    print("sending jump-to-boot...")
    send(dev, frame(JUMP_BOOT, CMD_DATA, size=8))
    print(f"sent. Device should re-enumerate as {VID:04x}:{PID_BOOT:04x} (bootloader).")


def do_info():
    dev = open_dev(PID_BOOT)
    if dev:
        print(f"bootloader {VID:04x}:{PID_BOOT:04x} present")
        send(dev, frame(SUB_GET_VERIF, CMD_DATA))
        vid = recv_reply(dev, 2, 0x19, "verification id")[5:5+VERIF_LEN]
        print("verification id:", vid.hex())
        print("encode-id:      ", encode_id(vid).hex())
        print("The bootloader answers this once per session: to flash now, pass\n"
              f"  flasher.py flash FILE.dat --verif-id {vid.hex()}")
        return
    dev = open_dev(PID_RUNTIME)
    if dev:
        print(f"runtime {VID:04x}:{PID_RUNTIME:04x} present (D-input). "
              "Run 'jump-boot' then 'info' again for the bootloader.")
        return
    sys.exit("no modkit found (runtime 2869 or bootloader 5750)")


def do_flash(datpath, verif_hex=None):
    raw = open(datpath, "rb").read()
    ver, addr, plen, pid = struct.unpack("<IIII", raw[:16])
    header = raw[:HDR]
    payload = raw[HDR:HDR+plen]
    print(f"image: v{ver} addr=0x{addr:08x} len={plen} ({len(payload)} payload bytes, ENCRYPTED)")

    dev = open_dev(PID_BOOT)
    if dev is None:
        sys.exit(f"bootloader {VID:04x}:{PID_BOOT:04x} not found — run 'jump-boot' first "
                 "(and wait for re-enumeration)")

    stale = drain(dev)
    if stale:
        print(f"discarded {stale} stale repl{'y' if stale == 1 else 'ies'}")
    # 1) verification id. The bootloader answers it once per session: if `info` already
    #    read it, pass the id it printed with --verif-id to go straight to the header.
    #    Its first 12 bytes come from the chip; the rest include 12 bytes the bootloader reads
    #    from the installed app (0xFF while the app area is erased).
    if verif_hex:
        vid = bytes.fromhex(verif_hex)
        print("verification id (given):", vid.hex())
    else:
        send(dev, frame(SUB_GET_VERIF, CMD_DATA))
        vid = recv_reply(dev, 2, 0x19, "verification id")[5:5+VERIF_LEN]
        print("verification id:", vid.hex())
    if len(vid) != VERIF_LEN:
        sys.exit(f"verification id must be {VERIF_LEN} bytes, got {len(vid)}")
    enc = encode_id(vid)
    print("encode-id:", enc.hex())

    # 2) header (the device erases the app area before ACKing: ~2.8 s in the capture)
    print("header (erase)...", flush=True)
    send(dev, frame(SUB_FLASH, CMD_HEADER, header)); expect_ack(dev, "header", timeout=20000)
    # 3) prepare
    send(dev, frame(SUB_PREPARE, CMD_DATA)); expect_ack(dev, "prepare")
    # 4) data chunks
    n = (len(payload) + CHUNK - 1) // CHUNK
    t0 = time.time()
    # As in the capture: every chunk is ACKed except the last -- the device sends a single
    # ACK after the last chunk + encode-id, so the encode-id goes out without waiting.
    for i in range(n):
        send(dev, frame(SUB_FLASH, CMD_DATA, payload[i*CHUNK:(i+1)*CHUNK]))
        if i < n - 1:
            expect_ack(dev, f"data {i+1}/{n}")
        if i % 128 == 0 or i == n-1:
            print(f"\r  {i+1}/{n} chunks", end="", flush=True)
    print()
    # 5) encode-id, 6) get version, 7) ok
    send(dev, frame(SUB_FLASH, CMD_ENCODE, enc)); expect_ack(dev, "last chunk + encode-id")
    send(dev, frame(SUB_FLASH, CMD_GETVER))
    r = recv_reply(dev, 5, CMD_GETVER, "version"); v = r[8] | r[9] << 8 if len(r) >= 10 else 0
    print(f"device reports version {v} after write")
    send(dev, frame(SUB_FLASH, CMD_OK))
    print(f"done in {time.time()-t0:.1f}s — power-cycle the controller.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("jump-boot")
    sub.add_parser("reset")
    fp = sub.add_parser("flash"); fp.add_argument("dat")
    fp.add_argument("--verif-id", metavar="HEX",
                    help="skip GET_VERIFICATION_ID (already answered this bootloader session by "
                         "'info') and use the id it printed")
    ep = sub.add_parser("encode-id"); ep.add_argument("verif_id", metavar="HEX")
    a = ap.parse_args()
    if a.cmd == "info": do_info()
    elif a.cmd == "jump-boot": do_jump_boot()
    elif a.cmd == "reset": do_reset()
    elif a.cmd == "flash": do_flash(a.dat, a.verif_id)
    elif a.cmd == "encode-id": print(encode_id(bytes.fromhex(a.verif_id)).hex())


if __name__ == "__main__":
    main()
