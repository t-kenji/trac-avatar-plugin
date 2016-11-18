#!/usr/bin/python
#
# Copyright (c) 2016, t-kenji
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the authors nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import io
import re
import struct

from PIL import Image
from colorhash import ColorHash

class PictureAvatar(object):
    """
    Picture avatar class.
    """
    
    def open(self, filename, mode='r'):
        return Image.open(filename, mode)

    def fromfiledata(self, fd, filename):
        """
        PIL.Image object from file data object.
        """

        fd.seek(0)
        prefix = fd.read(16)

        Image.preinit()

        def _open_core(fp, filename, prefix):
            for i in Image.ID:
                try:
                    factory, accept = Image.OPEN[i]
                    if not accept or accept(prefix):
                        fp.seek(0)
                        im = factory(fp, filename)
                        Image._decompression_bomb_check(im.size)
                        return im
                except (SyntaxError, IndexError, TypeError, struct.error):
                    continue
            return None

        im = _open_core(fd, filename, prefix)

        if im is None:
            if init():
                im = _open_core(fd, filename, prefix)

        if im:
            return im

        raise IOError('Cannot identify image file {}'.format(filename))

class InitialAvatar(object):
    """
    Initial avatar class.
    """

    SVG_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" pointer-events="none" width="{width}px" height="{height}px"
     style="width: {width}px; height: {height}px; background-color: {color};">
  <text text-anchor="middle" y="50%" x="50%" dy="0.36em" pointer-events="auto" fill="#ffffff"
        font-family="HelveticaNeue-Light,Helvetica Neue Light,Helvetica Neue,Helvetica, Arial,Lucida Grande, sans-serif"
        style="font-weight: 600; font-size: 64px;">
    {initial}
  </text>
</svg>"""

    def __init__(self, username):
        self.username = username
        self.template = self.SVG_TEMPLATE

    def set_template(self, template):
        if template:
            self.template = template

    def create(self, width, height):
        colors = ColorHash(self.username)

        svg_params = {
            'color': colors.hex,
            'initial': self.username[:2].upper(),
            'width': width,
            'height': height,
        }

        return self.template.format(**svg_params)

class SilhouetteAvatar(object):
    """
    Silhouette avatar class.
    """

    SVG_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<svg version="1.2" baseProfile="tiny" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     x="0px" y="0px" width="{width}px" height="{height}px" viewBox="0 0 256 256" xml:space="preserve">
<rect x="0" y="0" fill="{color}" width="256" height="256"/>
<path fill="#FFFFFF" d="M195.919,197.89c-31.472-11.47-41.529-21.144-41.529-41.861c0-12.435,9.611-8.374,13.827-31.149
    c1.751-9.447,10.237-0.152,11.864-21.719c0-8.593-4.632-10.731-4.632-10.731s2.354-12.722,3.275-22.508
    c1.141-12.2-7.045-43.712-50.725-43.712c-43.68,0-51.87,31.513-50.725,43.712c0.922,9.786,3.275,22.508,3.275,22.508
    s-4.632,2.138-4.632,10.731c1.62,21.567,10.109,12.272,11.856,21.719c4.225,22.776,13.827,18.714,13.827,31.149
    c0,20.717-10.049,30.391-41.521,41.861C28.509,209.396,8,221.124,8,229.123V256h120h120v-26.877
    C248,221.124,227.491,209.396,195.919,197.89"/>
</svg>"""

    def __init__(self, username):
        self.username = username
        self.template = self.SVG_TEMPLATE

    def set_template(self, template):
        if template:
            self.template = template

    def create(self, width, height):
        colors = ColorHash(self.username)

        svg_params = {
            'color': colors.hex,
            'width': width,
            'height': height,
        }

        return self.template.format(**svg_params)
