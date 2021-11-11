#! /usr/bin/env python3

# SPDX-License-Identifier: BSD-2-Clause
#
# Copyright (c) 2021 Alexandre Joannou
# All rights reserved.
#
# This software was developed by SRI International and the University of
# Cambridge Computer Laboratory (Department of Computer Science and
# Technology) under DARPA contract HR0011-18-C-0016 ("ECATS"), as part of the
# DARPA SSITH research programme.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#

import subprocess
import argparse
import pexpect
import time
import sys
import os

################################
# Parse command line arguments #
################################################################################

def auto_int(x):
  return int(x, 0)

def auto_pos_int(x):
  val = int(x, 0)
  if val <= 0:
    raise argparse.ArgumentTypeError("argument must be a positive int. Got {:d}.".format(val))
  return val

parser = argparse.ArgumentParser(description='Runs a DE10Pro session')

parser.add_argument ( '--hps-rbf', metavar='HPS_RBF'
                    , type=str, default='socfpga.hps.rbf'
                    , help="The rbf slice for initial ARM stratix10 conf. to be found on the host machine.")

parser.add_argument ( '--core-rbf', metavar='CORE_RBF'
                    , type=str, default='socfpga.core.rbf'
                    , help="The name of the rbf slice for fpga stratix10 conf. to be found on the boot sdcard / usb device.")

parser.add_argument ( '--use-block-device', metavar='BLOCK_DEVICE'
                    , type=str, choices=['mmc', 'usb'], default='mmc'
                    , help="The block device to use to search for files (mmc(default) or usb)")

parser.add_argument ( '--arm-bsd-loader', metavar='ARM_BSD_LOADER'
                    , type=str, default='efi/boot/bootaa64.efi'
                    , help="The name of the arm bsd loader to run on the hps arm core. to be found on the boot sdcard / usb device.")

parser.add_argument ( '--arm-bsd-kernel', metavar='ARM_BSD_KERNEL'
                    , type=str, default='kernel-arm64-s10'
                    , help="The name of the arm bsd kernel to run on the hps arm core. to be found on the boot sdcard / usb device.")

parser.add_argument( '-v', '--verbosity', metavar='VERB', type=auto_int
                   , default=1, help="set verbosity level")

steps = [ 'uboot'
        , 'uboot-load-rbf'
        , 'uboot-load-bsd-loader'
        , 'bsd-loader'
        , 'bsd' ]
parser.add_argument( '--to-step', metavar='STEP'
                   , type=str, default='bsd', choices=steps
                   , help="step to boot to, one of {:s}".format(str(steps)))

args = parser.parse_args()

####################
# helper functions #
################################################################################

######## a 'which' helper function
######## (from https://stackoverflow.com/a/377028)
def which (prg):
  def is_exe (fpath):
    return os.path.isfile (fpath) and os.access (fpath, os.X_OK)

  fpath, fname = os.path.split (prg)
  if fpath:
    if is_exe (prg):
      return prg
  else:
    for path in os.environ.get('PATH').split (os.pathsep):
      exe_file = os.path.join (path, prg)
      if is_exe (exe_file):
        return exe_file
  return None

def get_exec (prg):
  p = which (prg)
  if p == None:
    print ("'" + prg + "' executable not in path")
    exit (-1)
  return p

def get_file (fname):
  f = os.path.realpath (fname)
  if not os.path.exists(f):
    print ("'" + f + "' does not exist")
    exit (-1)
  return f

def vprint(lvl, msg):
  if args.verbosity >= lvl:
    print(msg)

#######################################
# DE10Pro session configuration class #
################################################################################

class DE10ProSessionConf:
  """A DE10Pro session configuration"""

  def __init__ (self, hps_rbf, core_rbf, arm_use_block_device, arm_bsd_loader, arm_bsd_kernel):
    ######## quartus conf.
    # fail if incomplete config.
    self.quartus_pgm = get_exec ('quartus_pgm')
    ######## rbf conf.
    self.core_rbf = core_rbf
    self.hps_rbf = get_file (hps_rbf)
    ######## serial terminal conf.
    self.serial_tty = get_file (os.path.join ('/dev', 'ttyUSB0'))
    self.picocom = get_exec ('picocom')
    ######## arm system boot
    self.arm_use_block_device = arm_use_block_device
    self.arm_bsd_loader_addr = 0x02000000
    self.arm_bsd_loader = arm_bsd_loader
    self.arm_device_tree_addr = 0x08000000
    self.arm_device_tree = 'socfpga_stratix10_de10_pro2.dtb'
    self.arm_bsd_kernel = arm_bsd_kernel
    ######## pexpect handle
    #self.logfile = open ('/tmp/de10pro-interact.log', 'w')
    self.logfile = sys.stdout
    self.handle = None

  def to_uboot (self):
    ######## program hps rbf
    c = subprocess.Popen ([ self.quartus_pgm
                          , '-m', 'jtag'
                          , '-o', 'P;' + self.hps_rbf + '@2' ])
    c.wait ()
    vprint (1, "=================================================")
    ######## connect to serial tty
    picocom_args = [ '-b', '115200', self.serial_tty ]
    c = pexpect.spawn ( self.picocom, picocom_args
            , encoding = 'utf-8')#, logfile = self.logfile)
    c.expect ('Hit any key to stop autoboot:')
    c.sendline ()
    c.expect ('.* #')
    self.handle = c
    vprint (1, "=================================================")

  def uboot_load_core_rbf (self):
    c = self.handle
    dev = self.arm_use_block_device
    if dev == 'usb':
      c.sendline ('usb start')
      c.expect ('.* #')
      print (c.before)
    c.sendline ('fatload ' + dev + ' 0:1 1000 ' + self.core_rbf)
    c.expect ('.* #')
    print (c.before)
    print (c.after)
    c.sendline ('fpga load 0 1000 ${filesize}')
    c.expect ('.* #')
    print (c.before)
    c.sendline ('bridge enable')
    c.expect ('.* #')
    print (c.before)
    vprint (1, "=================================================")

  def uboot_load_bsd_loader (self):
    c = self.handle
    dev = self.arm_use_block_device
    c.sendline ('fatload ' + dev + ' 0:1 ' + hex (self.arm_bsd_loader_addr)
                                           + ' ' + self.arm_bsd_loader)
    c.expect ('.* #')
    print (c.before)
    c.sendline ('fatload ' + dev + ' 0:1 ' + hex (self.arm_device_tree_addr)
                                           + ' ' + self.arm_device_tree)
    c.expect ('.* #')
    print (c.before)
    vprint (1, "=================================================")

  def uboot_boot_bsd_loader (self):
    c = self.handle
    c.sendline ('bootefi ' + hex (self.arm_bsd_loader_addr) + ' '
                           + hex (self.arm_device_tree_addr))
    #time.sleep (1)
    #for _ in range(20):
    #  c.sendline()
    #time.sleep (1)
    c.expect ('OK ')
    print (c.before)
    vprint (1, "=================================================")

  def bsd_loader_boot_kernel (self):
    c = self.handle
    fatdev = 'disk0s1:'
    ufsdev = 'disk0s2:'
    if self.arm_use_block_device == 'usb':
      fatdev = 'disk1s1:'
      ufsdev = 'disk1s2:'
    c.sendline ('load ' + fatdev + self.arm_bsd_kernel)
    c.expect ('OK ')
    #c.sendline ('fdt ls')
    #c.expect ('OK ')
    #c.sendline ('boot')
    #c.expect ('mountroot>')
    #c.sendline ('ufs:diskid/DISK-20090815198100000s2a')
    c.sendline ('set currdev=' + ufsdev)
    c.expect ('OK ')
    c.sendline ('include /boot/lua/loader.lua')
    c.expect ('Enter full pathname of shell or RETURN for /bin/sh:')
    c.sendline ()
    c.expect ('root@:/ #')
    vprint (1, "=================================================")

  def fallback (self):
    if self.handle:
      vprint (0, ">>>> falling back to interactive session <<<<")
      self.handle.interact ()
    else:
      print ("no active pexpect session")
      exit (-1)

################################################################################

if __name__ == "__main__":
  sess = DE10ProSessionConf ( args.hps_rbf
                            , args.core_rbf
                            , args.use_block_device
                            , args.arm_bsd_loader
                            , args.arm_bsd_kernel )
  stepFuns = [ sess.to_uboot
             , sess.uboot_load_core_rbf
             , sess.uboot_load_bsd_loader
             , sess.uboot_boot_bsd_loader
             , sess.bsd_loader_boot_kernel ]
  for step, stepFun in zip (steps, stepFuns):
    stepFun()
    if args.to_step == step:
      break
  sess.fallback()
