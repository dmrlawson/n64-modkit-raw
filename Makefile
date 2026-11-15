# Raw-stick firmware for the 8BitDo N64 Modkit, as a patch to the official v1.04 firmware.
#
#   make         download the official firmware from 8BitDo, check it, apply the patch
#   make flash   the above, then flash build/n64modkit-raw.dat (controller in bootloader mode)
#   make stock   flash the official firmware back
#   make info    read the controller's verification id (bootloader mode)
#   make clean
#
# Bootloader mode: power the controller on while holding L + R + Start, connected by USB.
# Flashing needs Python with pyusb (PYTHON=/path/to/python, or set it in local.mk).
-include local.mk
PYTHON ?= python3

URL    := http://dl.8bitdo.com:8080/firmwareFile/upload/2e7dc1b5-707c-4b94-bc71-e258505c608b.dat
SHA256 := 9d1675bea9b3848462434d1e4bea5fb4f9c2491d014ad382f0ab84defe7c3a19
PATCH  := n64modkit-raw-v1.04.patch
STOCK  := build/n64modkit-v1.04.dat
OUT    := build/n64modkit-raw.dat

.PHONY: all fetch patch flash stock info clean

all: patch
fetch: $(STOCK)
patch: $(OUT)

# The server is plain HTTP: the SHA-256 check is what makes this the official file.
$(STOCK):
	@mkdir -p build
	curl -fsS -o $@.part $(URL)
	echo "$(SHA256)  $@.part" | sha256sum -c -
	mv $@.part $@

$(OUT): $(STOCK) $(PATCH) apply_patch.py
	python3 apply_patch.py $(PATCH) $(STOCK) $@

flash: $(OUT)
	$(PYTHON) flasher.py flash $(OUT)

stock: $(STOCK)
	$(PYTHON) flasher.py flash $(STOCK)

info:
	$(PYTHON) flasher.py info

clean:
	rm -rf build
