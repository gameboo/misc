Prepare an sdcard with a fat partition and a bsd rootfs partition
For example, using cheribuild

../cheribuild/cheribuild.py --source-root=/home/gameboo/devstuff/cheri --freebsd/repository=https://github.com/CTSRD-CHERI/freebsd-morello --freebsd/git-revision=stratix10 --freebsd/toolchain=system-llvm freebsd-aarch64 disk-image-freebsd-aarch64

You can put files to add to the final bsd rootfs in /home/gameboo/devstuff/cheri
specifically, add a dtbo describing the uart and the /boot/loader.conf.local to
point to it

In the Fat partition, you want:

- a u-boot binary
- the `*.core.rbf` to use for the fpga configuration
- the dtb
- the efi bsd loader
- the bsd kernel to boot

In the bsd rootfs partition, you want:

- a bsd rootfs ;)
- loader script to include `/boot/lua/loader.lua`
- to detect the uart on the FPGA side:
  * a device tree overlay: `/boot/fpga-ns16550.dtbo`
  * a loader configuration `/boot/loader.conf.local` with the content
    `fdt_overlays="/boot/fpga-ns16550.dtbo"`
- possibly your ssh keys to help ssh-ing into the arm
- a clone of `https://github.com/bukinr/RISCV_gdbstub.git` to use gdb on the
  riscv core on the fpga
- a clone of `https://github.com/CTSRD-CHERI/fmem.git` to talk to the various
  fmem devices from the command line
- git / vim / gcc / whatever tools...

To embed a bootloader and get an hps and a core slice from a bitfile:
```
$ BOOTLOADER=<DE10Pro-hps-ubuntu-sdcard path>/u-boot-socfpga/spl/u-boot-spl-dtb.ihex
$ SOF=DE10Pro.sof
$ quartus_cpf --bootloader=$BOOTLOADER $SOF socfpga.sof
$ quartus_cpf -c --hps -o bitstream_compression=on socfpga.sof socfpga.rbf
```

To push the hps slice to the board and get a usb terminal going:
```
$ RBF=<quartus project path>/output_files/socfpga.hps.rbf
$ quartus_pgm -m jtag -o P\;$RBF@2 && picocom -b 115200 /dev/ttyUSB0
```

To get the core slice programmed from the sdcard and the AXI bus ready from u-boot:
```
fatload mmc 0:1 1000 <path to socfpga.core.rbf in sdcard mount partition>
fpga load 0 1000 ${filesize}
bridge enable
```

Other useful u-boot commands:
```
printenv
usb start
usb info
fatload usb ...
```

To get the bsd loader and device tree from the sdcard and boot into the bootloader,
from uboot:
```
fatload mmc 0:1 0x2000000 <path to loader.efi in sdcard mount partition>
fatload mmc 0:1 0x8000000 <path to socfpga_stratix10_de10_pro2.dtb in sdcard mount partition>
bootefi 0x2000000 0x8000000
```

To load the kernel from the sdcard and boot it, from the freebsd bootloader:
```
load <disk0s2a>:</boot/kernel/kernel>
fdt ls
boot
```

Other useful freebsd loader commands:
```
show
set currdev=disk1s2:
include /boot/lua/loader.lua
```

To specify the usb drive as the rootfs on freebsd boot:
```
ufs:diskid/DISK-20090815198100000s2a
```


in `/etc/rc.conf` add
 - ifconfig_<ifc aka dwc0>="inet a.b.c.d/24"
 - defaultrouter="a.b.c.1"
