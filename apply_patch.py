#!/usr/bin/env python3
"""Apply a byte patch to the official firmware file.

  apply_patch.py PATCH OFFICIAL.dat OUT.dat

The patch names the SHA-256 of the file it applies to and of the result; both are checked,
so it only applies to the exact official file and can only produce the intended one.
"""
import hashlib, sys


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    patch, src, out = sys.argv[1:4]
    data = bytearray(open(src, "rb").read())
    meta, edits = {}, []
    for line in open(patch):
        line = line.split("#")[0].split()
        if not line:
            continue
        if line[0] in ("size", "source-sha256", "result-sha256"):
            meta[line[0]] = line[1]
        else:
            edits.append((int(line[0], 16), bytes.fromhex(line[1])))
    if len(data) != int(meta["size"]) or sha256(data) != meta["source-sha256"]:
        sys.exit(f"patch: {src} is not the firmware this patch is for "
                 f"(SHA-256 {sha256(data)}, expected {meta['source-sha256']})")
    for off, new in edits:
        if off + len(new) > len(data):
            sys.exit(f"patch: edit at {off:#x} runs past the end of the file")
        data[off:off + len(new)] = new
    if sha256(data) != meta["result-sha256"]:
        sys.exit("patch: result has the wrong SHA-256 -- patch file damaged?")
    open(out, "wb").write(data)
    print(f"patch: {out} OK ({sum(len(n) for _, n in edits)} bytes changed, SHA-256 matches)")


if __name__ == "__main__":
    main()
