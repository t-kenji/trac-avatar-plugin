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

from pkg_resources import resource_filename

from trac.core import *
from trac.db import DatabaseManager
from trac.mimeview import *
from trac.prefs import IPreferencePanelProvider
from trac.util import get_reporter_id
from trac.util.translation import domain_functions
from trac.web.api import IRequestHandler
from trac.web.chrome import ITemplateProvider, add_notice, add_stylesheet

from PIL import Image
from colorhash import ColorHash

_, tag_, N_, add_domain = domain_functions('userprofile',
    '_', 'tag_', 'N_', 'add_domain')

def fromfiledata(fd, filename):
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
        if Image.init():
            im = _open_core(fd, filename, prefix)

    if im:
        return im

    raise IOError('Cannot identify image file {}'.format(filename))

class UserProfileModule(Component):

    AVATAR_WIDTH = 128
    AVATAR_HEIGHT = 128

    implements(IRequestHandler,
               IPreferencePanelProvider,
               ITemplateProvider)

    def __init__(self):
        # bind the 'userprofile' catalog to the locale directory
        add_domain(self.env.path, resource_filename(__name__, 'locale'))
        print(_('Now avatar').encode('utf-8'))

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        return [('userprofile', resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [resource_filename(__name__, 'templates')]

    def match_request(self, req):
        match = re.match(r'(?:/[\w\-/]+)?/avatar/\w+', req.path_info)
        return match

    def process_request(self, req):
        user = None
        match = re.search(r'(\w+)$', req.path_info)
        if match:
            user = match.groups(1)[0]

        if user:
            for filepath, in self.env.db_query("""
                                SELECT value FROM session_attribute
                                WHERE sid=%s AND name='avatar'
                                """,
                                (user,)):
                image = Image.open(filepath, 'r')
                mime_type = 'image/{}'.format(image.format)

                req.send_file(filepath, mime_type)
                return

        colors = ColorHash(user)
        svg_params = {
            'color': colors.hex,
            'initial': user[:2].upper(),
            'width': self.AVATAR_WIDTH,
            'height': self.AVATAR_HEIGHT,
        }
        svg = """\
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" pointer-events="none" width="{width}px" height="{height}px"
     style="width: {width}px; height: {height}px; background-color: {color};">
  <text text-anchor="middle" y="50%" x="50%" dy="0.36em" pointer-events="auto" fill="#ffffff"
        font-family="HelveticaNeue-Light,Helvetica Neue Light,Helvetica Neue,Helvetica, Arial,Lucida Grande, sans-serif"
        style="font-weight: 600; font-size: 64px;">
    {initial}
  </text>
</svg>
""".format(**svg_params)

        req.send(svg, 'image/svg+xml')

    # IPreferencePanelProvider methods
    # ITemplateProvider methods
    def get_preference_panels(self, req):
        yield ('avatar', _('Avatar'))

    def render_preference_panel(self, req, panel):
        author = get_reporter_id(req, 'author')

        if req.method == 'POST':
            if req.args.has_key('user_profile_avatar_initialize'):
                if req.session['avatar']:
                    del req.session['avatar']

                    req.redirect(req.href.prefs(panel or None))
                    return

            if req.args.has_key('user_profile_avatar'):
                upload = req.args.get('user_profile_avatar', None)
                if upload is None or not hasattr(upload, 'filename') or not upload.filename:
                    raise TracError(_('No file uploaded'))
                
                if hasattr(upload.file, 'fileno'):
                    size = os.fstat(upload.file.fileno())[6]
                else:
                    upload.file.seek(0, 2) # seek to end of file
                    size = upload.file.tell()
                    upload.file.seek(0)
                if size == 0:
                    raise TracError(_('Can\'t upload empty file'))

                filename = upload.filename
                filename = filename.replace('\\', '/')
                filename = os.path.basename(filename)

                try:
                    image = fromfiledata(upload.file, filename)
                except:
                    raise TracError(_('Can\'t upload non image file'))

                avatar_dir = os.path.join(os.path.normpath(self.env.path), 'files', 'avatars')
                if not os.access(avatar_dir, os.F_OK):
                    os.makedirs(avatar_dir)
                filepath = u'{}/{}'.format(avatar_dir, author)

                req.session['avatar'] = filepath

                if image.width > self.AVATAR_WIDTH or image.height > self.AVATAR_HEIGHT:
                    image.thumbnail((self.AVATAR_WIDTH, self.AVATAR_HEIGHT))
                image.save(filepath, image.format)
                self.env.log.info('New avatar uploaded by {}'.format(author))

            req.redirect(req.href.prefs(panel or None))

        return 'prefs_avatar.html', {
            '_': _,
            'user': {
                'avatar_href': '{}/avatar/{}'.format(self.env.href(), author),
            },
        }
