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
import hashlib
import itertools

from pkg_resources import resource_filename

from trac.core import *
from trac.config import Option
from trac.db import DatabaseManager
from trac.mimeview import *
from trac.prefs import IPreferencePanelProvider
from trac.util import get_reporter_id
from trac.util.translation import domain_functions
from trac.web.api import IRequestHandler, ITemplateStreamFilter
from trac.web.chrome import ITemplateProvider, add_stylesheet
from genshi.filters.transform import Transformer
from genshi.builder import tag

from image import PictureAvatar, InitialAvatar

_, tag_, N_, add_domain = domain_functions('avatar',
    '_', 'tag_', 'N_', 'add_domain')

class AvatarModule(Component):
    implements(ITemplateStreamFilter, ITemplateProvider)

    ticket_reporter_size = Option("avatar", "ticket_reporter_size", default="60")
    ticket_comment_size = Option("avatar", "ticket_comment_size", default="40")
    ticket_comment_diff_size = Option("avatar", "ticket_comment_size", default="40")
    timeline_size = Option("avatar", "timeline_size", default="30")
    browser_lineitem_size = Option("avatar", "browser_lineitem_size", default="20")
    browser_changeset_size = Option("avatar", "browser_changeset_size", default="40")
    prefs_form_size = Option("avatar", "prefs_form_size", default="40")
    metanav_size = Option("avatar", "metanav_size", default="30")
    default = Option('avatar', 'avatar_default', default='default',
                            doc="The default value to pass along to avatar to "
                            "use if the email address does not match.")
    backend = Option('avatar', 'backend', default='built-in',
                            doc="The name of the avatar service to use as a "
                            "backend.  Currently built-in, gravatar and libravatar "
                            "are supported.")

    # A mapping of possible backends to their peculiarities
    external_backends = {
        "gravatar": {
            "url": "gravatar.com",
            "base": "http://www.gravatar.com/avatar/",
            "base_ssl": "https://gravatar.com/avatar/",
        },
        "libravatar": {
            "url": "libravatar.org",
            "base": "http://cdn.libravatar.org/avatar/",
            "base_ssl": "https://seccdn.libravatar.org/avatar/",
        },
    }

    backends = {}

    def __init__(self):
        abs_href = self.env.abs_href()
        match = re.match(r'https?://(?P<domain>[\w\d\.\-_\:]+)(?P<subdirectory>/[\w\d\.\-_/]*)?', abs_href)
        if match.lastgroup == 'subdirectory':
            url = '{}{}/prefs/avatar'.format(match.group('domain'), match.group('subdirectory'))
            base = 'http://{}{}/avatar/'.format(match.group('domain'), match.group('subdirectory'))
            base_ssl = 'https://{}{}/avatar/'.format(match.group('domain'), match.group('subdirectory'))
        else:
            url = '{}/prefs/avatar'.format(match.group('domain'))
            base = 'http://{}/avatar/'.format(match.group('domain'))
            base_ssl = 'https://{}/avatar/'.format(match.group('domain'))

        builtin = {
            'url': url,
            'base': base,
            'base_ssl': base_ssl,
        }
        self.backends.update({ 'built-in': builtin })
        self.backends.update(self.external_backends)

        if not self.env.is_component_enabled(AvatarProvider):
            if self.backend == 'built-in':
                self.config.set('avatar', 'backend', 'gravatar')

    def filter_stream(self, req, method, filename, stream, data):
        filter_ = []
        author_data = {}
        context = {
            'is_https': req.base_url.startswith("https://"),
            'author_data': author_data,
            'data': data,
            'query': req.query_string,
        }

        filter_.extend(self._metanav(req, context))

        if req.path_info.startswith("/ticket"):
            filter_.extend(self._ticket_filter(context))
        elif req.path_info.startswith("/timeline"):
            filter_.extend(self._timeline_filter(context))
        elif req.path_info.startswith("/browser"):
            filter_.extend(self._browser_filter(context))
        elif req.path_info.startswith("/log"):
            filter_.extend(self._log_filter(context))
        elif self.backend != 'built-in' and req.path_info == "/prefs":
            filter_.extend(self._prefs_filter(context))

        self._lookup_email(author_data)
        for f in filter_:
            if f is not None:
                stream |= f
        add_stylesheet(req, 'avatar/css/avatar.css')
        return stream

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        yield 'avatar', resource_filename(__name__, 'htdocs')

    def get_templates_dirs(self):
        return []

    def _metanav(self, req, context):
        data = req.session

        if 'email' not in data:
            return []

        email = data['email']

        return [Transformer('//*/div[@id="metanav"]/ul/li[@class="first"]').prepend(
            self._generate_avatar(
                context,
                email,
                "metanav-avatar",
                self.metanav_size)),
        ]

    def _generate_avatar(self, context, author, class_, size):
        author_data = context['author_data']
        email_hash = author_data.get(author, None) or self._avatar_slug(author)
        if context['is_https']:
            href = self.backends[self.backend]['base_ssl'] + email_hash
        else:
            href = self.backends[self.backend]['base'] + email_hash
        href += "?size=%s" % size
        # for some reason sizing doesn't work if you pass "default=default"
        if self.default != 'default':
            href += "&default=%s" % (self.default,)
        return tag.img(src=href, class_='avatar %s' % class_, width=size, height=size).generate()

    def _ticket_filter(self, context):
        query = context.get('query', '')
        filter_ = []
        if "action=comment-diff" in query:
            filter_.extend(self._ticket_comment_diff_filter(context))
        else:
            filter_.extend(self._ticket_reporter_filter(context))
            filter_.extend(self._ticket_comment_filter(context))
        return filter_

    def _browser_filter(self, context):
        data, author_data = context['data'], context['author_data']
        filter_ =[]
        if not data.get('dir'):
            filter_.extend(self._browser_changeset_filter(context))
        else:
            filter_.extend(self._browser_lineitem_filter(context))
        return filter_

    def _browser_changeset_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'file' not in data or \
            not data['file'] or \
            'changeset' not in data['file']:
            return
        author = data['file']['changeset'].author
        author_data[author]  = None
        return [lambda stream: Transformer('//table[@id="info"]//th').prepend(
                self._generate_avatar(
                        context,
                        author,
                        "browser-changeset",
                        self.browser_changeset_size))(stream),
        ]

    def _prefs_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'settings' not in data or \
            'session' not in data['settings'] or \
            'email' not in data['settings']['session']:
            email = ''
        else:
            email = data['settings']['session']['email']

        return [Transformer('//form[@id="userprefs"]/table').append(
                tag.tr(
                        tag.th(
                                tag.label(
                                        self.backend.title() + ":",
                                        for_="avatar",
                                ),
                        ),
                        tag.td(
                                self._generate_avatar(
                                        context,
                                        email,
                                        "prefs-avatar",
                                        self.prefs_form_size),
                                " Change your avatar at ",
                                tag.a(
                                        self.backends[self.backend]['url'],
                                        href="http://" + self.backends[self.backend]['url'],
                                ),
                                class_="avatar prefs-avatar",
                        ),
                        class_="field",
                )),
        ]

    def _log_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'changes' not in data:
            return
        for change in data['changes'].values():
            author_data[change.author] = None
        return self._browser_lineitem_render_filter(context)

    def _browser_lineitem_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'dir' not in data or 'changes' not in data['dir']:
            return
        for trac_cset in data['dir']['changes'].values():
            author_data[trac_cset.author] = None
        return self._browser_lineitem_render_filter(context)

    def _browser_lineitem_render_filter(self, context):
        data, author_data = context['data'], context['author_data']
        def find_change(stream):
            author = stream[1][1]
            tag = self._generate_avatar(
                context,
                author,
                'browser-lineitem',
                self.browser_lineitem_size)
            return itertools.chain([stream[0]], tag, stream[1:])

        return [Transformer('//td[@class="author"]').filter(find_change)]

    def _ticket_reporter_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'ticket' not in data:
            return
        author = data['ticket'].values['reporter']
        author_data[author] = None

        return [lambda stream: Transformer('//div[@id="ticket"]').prepend(
                self._generate_avatar(
                        context,
                        author,
                        'ticket-reporter',
                        self.ticket_reporter_size))(stream),
        ]

    def _ticket_comment_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'changes' not in data:
            return

        apply_authors = []
        for change in data['changes']:
            try:
                author = change['author']
            except KeyError:
                continue
            else:
                author_data[author] = None
                apply_authors.insert(0, author)

        def find_change(stream):
            stream = iter(stream)
            author = apply_authors.pop()
            tag = self._generate_avatar(
                        context,
                        author,
                        'ticket-comment',
                        self.ticket_comment_size)
            return itertools.chain([next(stream)], tag, stream)

        return [Transformer('//div[@id="changelog"]/div[@class="change"]/h3[@class="change"]').filter(find_change)]

    def _ticket_comment_diff_filter(self, context):
        data, author_data = context['data'], context['author_data']

        author = data['change']['author']
        author_data[author] = None
        return [lambda stream: Transformer('//dd[@class="author"]').prepend(
                self._generate_avatar(
                        context,
                        author,
                        "ticket-comment-diff",
                        self.ticket_comment_diff_size))(stream),
        ]

    def _timeline_filter(self, context):
        data, author_data = context['data'], context['author_data']
        if 'events' not in data:
            return

        apply_authors = []
        for event in reversed(data['events']):
            author = event['author']
            author_data[author] = None
            apply_authors.append(author)

        def find_change(stream):
            stream = iter(stream)
            author = apply_authors.pop()
            tag = self._generate_avatar(
                        context,
                        author,
                        'timeline',
                        self.timeline_size)
            return itertools.chain(tag, stream)

        return [Transformer('//div[@id="content"]/dl/dt/a/span[@class="time"]').filter(find_change)]

    # from trac source
    _long_author_re = re.compile(r'.*<([^@]+)@([^@]+)>\s*|([^@]+)@([^@]+)')

    def _avatar_slug(self, email):
        if email is None:
            email = ''
        return hashlib.md5(email.lower()).hexdigest()

    def _lookup_email(self, author_data):
        author_names = [a for a in author_data if a]
        lookup_authors = sorted([a for a in author_names if '@' not in a])
        email_authors = set(author_names).difference(lookup_authors)

        if lookup_authors:
            for sid, email in self.env.db_query("""
                    SELECT sid, value FROM session_attribute
                    WHERE name=%%s AND sid IN (%s)
                    """ % ','.join(['%s'] * len(lookup_authors)),
                    ('email',) + tuple(lookup_authors)):
                author_data[sid] = self._avatar_slug(email)

        for author in email_authors:
            author_info = self._long_author_re.match(author)
            if author_info:
                if author_info.group(1):
                    name, host = author_info.group(1, 2)
                elif author_info.group(3):
                    name, host = author_info.group(3, 4)
                else:
                    continue
                author_data[name] = \
                    author_data[author] = \
                    self._avatar_slug("%s@%s" % (name, host))

class AvatarProvider(Component):

    AVATAR_WIDTH = 128
    AVATAR_HEIGHT = 128

    implements(IRequestHandler,
               IPreferencePanelProvider,
               ITemplateProvider)

    def __init__(self):
        # bind the 'avatar' catalog to the locale directory
        add_domain(self.env.path, resource_filename(__name__, 'locale'))

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        return [('avatar', resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [resource_filename(__name__, 'templates')]

    def match_request(self, req):
        match = re.match(r'(?:/[\w\-/]+)?/avatar/\w+', req.path_info)
        return match

    def process_request(self, req):
        username = 'anonymous'
        match = re.search(r'(\w+)$', req.path_info)
        if match:
            email_hash = match.groups(1)[0]

        if email_hash:
            for sid, email, in self.env.db_query("""
                    SELECT sid, value FROM session_attribute
                    WHERE name='email'
                    """):
                if sid == email_hash \
                   or email == email_hash \
                   or hashlib.md5(sid.lower()).hexdigest() == email_hash \
                   or hashlib.md5(email.lower()).hexdigest() == email_hash:

                    result = self.env.db_query("""
                            SELECT value FROM session_attribute
                            WHERE name='avatar' AND sid=%s
                            """,
                            (sid,))
                    if result is not None and len(result) > 0:
                        filepath, = result[0]
                        image = PictureAvatar().open(filepath, 'r')
                        mime_type = 'image/{}'.format(image.format)

                        req.send_file(filepath, mime_type)
                        return
                    else:
                        username = sid

        ia = InitialAvatar(username)
        req.send(ia.create(self.AVATAR_WIDTH, self.AVATAR_HEIGHT), 'image/svg+xml')

    # IPreferencePanelProvider methods

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
                    image = PictureAvatar().fromfiledata(upload.file, filename)
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
