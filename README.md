# N64 Modkit raw-stick firmware

An unofficial patch for the **8BitDo N64 Modkit** firmware (v1.04). Not affiliated with or
endorsed by 8BitDo. No 8BitDo firmware is in this repository: `make` downloads the official
file from 8BitDo's server and changes 1,236 of its 80,924 bytes.

What the patched firmware does differently:

- **Raw stick:** each axis is sent as `0x7F + encoder count`, the value an original N64
  controller would report, instead of being auto-calibrated and scaled to 0–255.
- **L + R + Start recentres the stick**, as on an original controller.
- **Switch (S) mode reports every 5 ms** over Bluetooth instead of every 15 ms.
- **Switch-mode Bluetooth name is "N64 Controller Raw"**, so an adapter can tell that the
  stick values need no further scaling. A modified BlueRetro (branch `n64-modkit-raw`)
  uses this to pass them straight to an N64.

Rumble and everything else are as in the official firmware.

## Use

Needs `make`, `curl`, `sha256sum`, Python 3, and for flashing Python with `pyusb`.
On Linux, install the udev rule once so flashing needs no root:

    sudo cp 99-8bitdo.rules /etc/udev/rules.d/ && sudo udevadm control --reload

Then, with the controller connected by USB and powered on **while holding L + R + Start**
(bootloader mode):

    make flash          # or: make flash PYTHON=/path/to/python-with-pyusb

`make stock` flashes the official firmware back. Flashing never touches the bootloader, so
a failed flash can be repeated from bootloader mode. This is at your own risk.

The patch only applies to the exact official v1.04 file: its SHA-256 is checked before
patching and the result's SHA-256 after.
