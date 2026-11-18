# N64 Modkit raw-stick firmware

An unofficial firmware patch for the **8BitDo N64 Modkit** (firmware v1.04). The patch
makes the Modkit send the same stick values as an original N64 controller. With a
[modified BlueRetro](https://github.com/dmrlawson/BlueRetro/tree/n64-modkit-raw) adapter,
an N64 console gets these values without changes.

This project is not affiliated with 8BitDo, and 8BitDo does not endorse it.

## Why

The official firmware calibrates the stick automatically and scales each axis to 0–255.
A Bluetooth adapter for the N64 must then scale the values down again to the N64 range.
After these two conversions, the console does not get the values that an original
controller sends. The stick range and the stick response are different.

The patched firmware does not calibrate and does not scale. It sends the count from the
stick encoders, as an original controller does.

## What the patch changes

| | Official v1.04 | With this patch |
|---|---|---|
| Stick values | Calibrated automatically, scaled to 0–255 | Raw: `0x7F + encoder count` |
| Stick centre | Set by the automatic calibration | Set by L + R + Start |
| Report interval in Switch (S) mode | 15 ms | 5 ms |
| Bluetooth name in Switch (S) mode | The 8BitDo name | `N64 Controller Raw` |

Rumble and all other functions are the same as in the official firmware.

## Benefits

- **The stick response of an original controller.** The console gets the same range and
  the same step size as it gets from an original controller. One encoder step is one
  step in the game.
- **No automatic calibration.** The firmware does not adjust the stick values.
- **Stick centre when you want it.** Push L + R + Start to set the centre, as on an
  original controller.
- **Less delay.** In Switch (S) mode, the controller sends a report each 5 ms. The
  official firmware sends a report each 15 ms. The 5 ms interval was measured through
  USB only, not through Bluetooth.
- **Automatic detection by the adapter.** The modified BlueRetro finds the name
  `N64 Controller Raw` and sends the stick values to the N64 without scaling. Images for
  the adapter are on its [releases page](https://github.com/dmrlawson/BlueRetro/releases).
- **You can go back.** `make stock` installs the official firmware again.

## Install

You must have `make`, `curl`, `sha256sum` and Python 3. To flash, Python must have
`pyusb`.

1. On Linux, install the udev rule. Do this one time. Then you can flash without root.

       sudo cp 99-8bitdo.rules /etc/udev/rules.d/ && sudo udevadm control --reload

2. Put the controller in bootloader mode: connect USB, then set power to on while you
   hold L + R + Start.

3. Flash the patched firmware.

       make flash          # or: make flash PYTHON=/path/to/python-with-pyusb

`make` without a target downloads the official file and applies the patch, but does not
flash. `make stock` flashes the official firmware.

## Safety

- No 8BitDo firmware is in this repository. `make` downloads the official file from the
  8BitDo server and changes 1,236 of its 80,924 bytes.
- The patch applies to the exact official v1.04 file only. The SHA-256 of the official
  file is checked before the patch is applied. The SHA-256 of the result is checked
  after.
- The flasher does not write to the bootloader. If a flash fails, put the controller in
  bootloader mode and flash again.
- You use this patch at your own risk.

## Licence

The scripts and the patch are under the MIT licence (see `LICENSE`). The firmware that
they change is the property of 8BitDo, and the MIT licence does not apply to it.
