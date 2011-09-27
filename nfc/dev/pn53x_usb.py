# -*- coding: latin-1 -*-
# -----------------------------------------------------------------------------
# Copyright 2009-2011 Stephen Tiedemann <stephen.tiedemann@googlemail.com>
#
# Licensed under the EUPL, Version 1.1 or - as soon they 
# will be approved by the European Commission - subsequent
# versions of the EUPL (the "Licence");
# You may not use this work except in compliance with the
# Licence.
# You may obtain a copy of the Licence at:
#
# http://www.osor.eu/eupl
#
# Unless required by applicable law or agreed to in
# writing, software distributed under the Licence is
# distributed on an "AS IS" basis,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied.
# See the Licence for the specific language governing
# permissions and limitations under the Licence.
# -----------------------------------------------------------------------------
#
# pn53x_usb.py - general support for NXP PN53x NFC chips with USB interface
#

import logging
log = logging.getLogger(__name__)

import usb
import sys
import pn53x

class pn53x_usb(object):
    def __init__(self, dev):
        self.dh = dev.open()
        self.usb_out = None
        self.usb_inp = None
        self.dh.setConfiguration(dev.configurations[0])
        self.dh.claimInterface(0)
        intf = dev.configurations[0].interfaces[0]
        self.usb_out = intf[0].endpoints[0].address
        self.usb_inp = intf[0].endpoints[1].address

        # try to get chip into a good state
        self.write(bytearray("\x00\x00\xFF\x00\xFF\x00")) # ack

    def close(self):
        self.dh.releaseInterface()
        self.dh = None

    def __del__(self):
        if self.dh and self.usb_out and self.usb_inp:
            rf_off = "\x00\x00\xff\x04\xfc\xd4\x32\x01\x00\xf9\x00"
            self.dh.bulkWrite(self.usb_out, rf_off)
            self.dh.bulkRead(self.usb_inp, 256, 100)
        
    def write(self, frame):
        if self.dh is not None and self.usb_out is not None:
            log.debug(">>> " + str(frame).encode("hex"))
            self.dh.bulkWrite(self.usb_out, frame)
            if len(frame) % 64 == 0:
                # send zero-length frame to end bulk transfer
                self.dh.bulkWrite(self.usb_out, '')

    def read(self, timeout):
        if self.dh is not None and self.usb_inp is not None:
            try: frame = self.dh.bulkRead(self.usb_inp, 300, timeout)
            except usb.USBError as error:
                if (error.args[0] == "No error" or
                    error.args[0] == "usb_reap: timeout error"):
                    # normal timeout condition on Linux (1) and Windows (2)
                    return None
                usb_err = "could not set config 1: Device or resource busy"
                if (error.args[0] == usb_err):
                    # timeout error if two readers used on same computer
                    return None
                log.error(error.args[0])
                return None
            else:
                frame = bytearray(frame)
                log.debug("<<< " + str(frame).encode("hex"))
                return frame

class Device(pn53x.Device):
    def __init__(self, dev):
        super(Device, self).__init__(dev)

    def listen(self, general_bytes, timeout):
        try:
            data = super(Device, self).listen(general_bytes, timeout)
        except pn53x.NoResponse:
            self.dev.bus.write(pn53x.pn53x.ACK)
        else:
            speed = ("106", "212", "424")[(data[0]>>4) & 0x07]
            cmode = ("passive", "active", "passive")[data[0] & 0x03]
            ttype = ("card", "p2p")[bool(data[0] & 0x04)]
            info = "activated as {0} target in {1} kbps {2} mode"
            log.info(info.format(ttype, speed, cmode))
            return str(data[18:])
            
def init(dev):
    bus = pn53x_usb(dev)
    dev = pn53x.pn53x(bus)
    return Device(dev)
