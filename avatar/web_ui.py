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
from trac.ticket.model import Ticket
from trac.resource import ResourceNotFound
from trac.util import get_reporter_id
from trac.util.translation import domain_functions
from trac.web.api import IRequestHandler, ITemplateStreamFilter
from trac.web.chrome import ITemplateProvider, add_script, add_stylesheet
from genshi.filters.transform import Transformer
from genshi.builder import tag

from image import PictureAvatar, InitialAvatar, SilhouetteAvatar
from backend import AvatarBackend

_, tag_, N_, add_domain = domain_functions('avatar',
    '_', 'tag_', 'N_', 'add_domain')

class AvatarModule(Component):

    implements(ITemplateStreamFilter, ITemplateProvider)

    ticket_reporter_size = Option('avatar', 'ticket_reporter_size', default='60')
    ticket_owner_size = Option('avatar', 'ticket_owner_size', default='20')
    ticket_comment_size = Option('avatar', 'ticket_comment_size', default='24')
    ticket_comment_diff_size = Option('avatar', 'ticket_comment_diff_size', default='20')
    ticket_comment_history_size = Option('avatar', 'ticket_comment_history_size', default='20')
    report_size = Option('avatar', 'report_size', default='20')
    timeline_size = Option('avatar', 'timeline_size', default='20')
    browser_lineitem_size = Option('avatar', 'browser_lineitem_size', default='20')
    browser_changeset_size = Option('avatar', 'browser_changeset_size', default='24')
    wiki_version_size = Option('avatar', 'wiki_version_size', default='20')
    wiki_diff_size = Option('avatar', 'wiki_diff_size', default='20')
    wiki_history_size = Option('avatar', 'wiki_history_size', default='20')
    attachment_view_size = Option('avatar', 'attachment_view_size', default='20')
    attachment_lineitem_size = Option('avatar', 'attachment_lineitem_size', default='20')
    search_results_size = Option('avatar', 'search_results_size', default='20')
    prefs_form_size = Option('avatar', 'prefs_form_size', default='40')
    metanav_size = Option('avatar', 'metanav_size', default='22')
    select_backend = Option('avatar', 'backend', default='built-in',
                     doc="The name of the avatar service to use as a "
                         "backend.  Currently built-in, gravatar and libravatar "
                         "are supported.")
    show_avatar_detail = Option('avatar', 'show_avatar_detail', default='disabled')

    def __init__(self):

        if not self.env.is_component_enabled(AvatarProvider):
            if self.select_backend == 'built-in':
                self.config.set('avatar', 'backend', 'gravatar')

        self.backend = AvatarBackend(self.env, self.config)

    def filter_stream(self, req, method, filename, stream, data):
        filter_ = []
        context = {
            'data': data,
            'query': req.query_string,
        }
        self.backend.clear_auth_data()

        filter_.extend(self._metanav(req, context))

        if req.path_info.startswith('/ticket'):
            filter_.extend(self._ticket_filter(context))
        elif req.path_info.startswith('/report') or req.path_info.startswith('/query'):
            filter_.extend(self._report_filter(context))
        elif req.path_info.startswith('/timeline'):
            filter_.extend(self._timeline_filter(context))
        elif req.path_info.startswith('/browser'):
            filter_.extend(self._browser_filter(context))
        elif req.path_info.startswith('/log'):
            filter_.extend(self._log_filter(context))
        elif req.path_info.startswith('/search'):
            filter_.extend(self._search_filter(context))
        elif req.path_info.startswith('/wiki'):
            filter_.extend(self._wiki_filter(context))
        elif req.path_info.startswith('/attachment'):
            filter_.extend(self._attachment_filter(context))
        elif self.select_backend != 'built-in' and req.path_info == '/prefs':
            filter_.extend(self._prefs_filter(context))

        if 'attachments' in data and data.get('attachments', {}).get('attachments'):
            filter_.extend(self._page_attachments_filter(context))

        self.backend.lookup_author_data()
        for f in filter_:
            if f is not None:
                stream |= f

        if self.show_avatar_detail == 'enabled':
            add_script(req, 'avatar/js/avatar.js')
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

        xpath = '//*/div[@id="metanav"]/ul/li[@class="first"]'
        return [Transformer(xpath).prepend(
            self.backend.generate_avatar(
                email,
                'metanav-avatar',
                self.metanav_size)),
        ]

    def _ticket_filter(self, context):
        query = context.get('query', '')
        filter_ = []
        if 'action=comment-diff' in query:
            filter_.extend(self._ticket_comment_diff_filter(context))
        elif 'action=comment-history' in query:
            filter_.extend(self._ticket_comment_history_filter(context))
        else:
            filter_.extend(self._ticket_reporter_filter(context))
            filter_.extend(self._ticket_owner_filter(context))
            filter_.extend(self._ticket_comment_filter(context))

        return filter_

    def _report_filter(self, context):
        data = context['data']
        if 'tickets' not in data and 'row_groups' not in data:
            return []

        if 'tickets' in data:
            class_ = 'query'
        elif 'row_groups' in data:
            class_ = 'report'

        def find_change(stream):
            author = ''.join(stream_part[1] for stream_part in stream if stream_part[0] == 'TEXT').strip()
            tag = self.backend.generate_avatar(
                        author,
                        class_,
                        self.report_size)
            return itertools.chain([stream[0]], tag, stream[1:])

        xpath = '//table[@class="listing tickets"]/tbody/tr/td[@class="owner"]|//table[@class="listing tickets"]/tbody/tr/td[@class="reporter"]'
        return [Transformer(xpath).filter(find_change)]

    def _browser_filter(self, context):
        data = context['data']
        filter_ =[]
        if not data.get('dir'):
            filter_.extend(self._browser_changeset_filter(context))
        else:
            filter_.extend(self._browser_lineitem_filter(context))
        return filter_

    def _browser_changeset_filter(self, context):
        data = context['data']
        if 'file' not in data or \
            not data['file'] or \
            'changeset' not in data['file']:
            return []
        author = data['file']['changeset'].author
        self.backend.collect_author(author)
        xpath = '//table[@id="info"]//th'
        return [lambda stream: Transformer(xpath).prepend(
                self.backend.generate_avatar(
                        author,
                        'browser-changeset',
                        self.browser_changeset_size))(stream),
        ]

    def _prefs_filter(self, context):
        data = context['data']
        if 'settings' not in data or \
            'session' not in data['settings'] or \
            'email' not in data['settings']['session']:
            email = ''
        else:
            email = data['settings']['session']['email']

        backend_ = self.backend.get_backend()
        xpath = '//form[@id="userprefs"]/table'
        return [Transformer(xpath).append(
                tag.tr(
                        tag.th(
                                tag.label(
                                        self.select_backend.title() + ':',
                                        for_='avatar',
                                ),
                        ),
                        tag.td(
                                self.backend.generate_avatar(
                                        email,
                                        'prefs-avatar',
                                        self.prefs_form_size),
                                ' Change your avatar at ',
                                tag.a(
                                        backend_['url'],
                                        href='http://' + backend_['url'],
                                ),
                                class_='avatar prefs-avatar',
                        ),
                        class_="field",
                )),
        ]

    def _log_filter(self, context):
        data = context['data']
        if 'changes' not in data:
            return []
        for change in data['changes'].values():
            self.backend.collect_author(change.author)
        return self._browser_lineitem_render_filter(context)

    def _search_filter(self, context):
        data = context['data']
        if 'results' not in data:
            return []

        def _find_result(stream):
            author = ''.join(stream_part[1] for stream_part in stream if stream_part[0] == 'TEXT').strip() ## As a fallback.
            tag = self.backend.generate_avatar(
                        author,
                        'search-results',
                        self.search_results_size)
            return itertools.chain([stream[0]], tag, stream[1:])

        xpath = '//dl[@id="results"]//span[@class="trac-author-user" or @class="trac-author"]'
        return [Transformer(xpath).filter(_find_result)]

    def _browser_lineitem_filter(self, context):
        data = context['data']
        if 'dir' not in data or 'changes' not in data['dir']:
            return []
        for trac_cset in data['dir']['changes'].values():
            self.backend.collect_author(trac_cset.author)
        return self._browser_lineitem_render_filter(context)

    def _browser_lineitem_render_filter(self, context):
        data = context['data']
        def find_change(stream):
            author = stream[1][1]
            tag = self.backend.generate_avatar(
                author,
                'browser-lineitem',
                self.browser_lineitem_size)
            return itertools.chain([stream[0]], tag, stream[1:])

        xpath = '//td[@class="author"]'
        return [Transformer(xpath).filter(find_change)]

    def _ticket_reporter_filter(self, context):
        data = context['data']
        if 'ticket' not in data:
            return []
        author = data['ticket'].values['reporter']
        self.backend.collect_author(author)

        xpath = '//div[@id="ticket"]'
        return [lambda stream: Transformer(xpath).prepend(
                self.backend.generate_avatar(
                        author,
                        'ticket-reporter',
                        self.ticket_reporter_size))(stream),
        ]

    def _ticket_owner_filter(self, context):
        data = context['data']
        if 'ticket' not in data:
            return []
        author = data['ticket'].values['owner']
        self.backend.collect_author(author)

        xpath = '//td[@headers="h_owner"]'
        return [lambda stream: Transformer(xpath).prepend(
                self.backend.generate_avatar(
                        author,
                        'ticket-owner',
                        self.ticket_owner_size))(stream),
        ]

    def _ticket_comment_filter(self, context):
        data = context['data']
        if 'changes' not in data:
            return []

        apply_authors = []
        for change in data['changes']:
            try:
                author = change['author']
            except KeyError:
                continue
            else:
                self.backend.collect_author(author)
                apply_authors.insert(0, author)

        def _find_change(stream):
            stream = iter(stream)
            author = apply_authors.pop()
            tag = self.backend.generate_avatar(
                    author,
                    'ticket-comment',
                    self.ticket_comment_size)
            return itertools.chain([next(stream)], tag, stream)

        xpath = '//div[@id="changelog"]/div[@class="change"]/h3[@class="change"]'
        return [Transformer(xpath).filter(_find_change)]

    def _ticket_comment_diff_filter(self, context):
        data = context['data']

        author = data['change']['author']
        self.backend.collect_author(author)
        xpath = '//dd[@class="author"]'
        return [lambda stream: Transformer(xpath).prepend(
                self.backend.generate_avatar(
                        author,
                        'ticket-comment-diff',
                        self.ticket_comment_diff_size))(stream),
        ]

    def _ticket_comment_history_filter(self, context):
        data = context['data']
        if 'history' not in data:
            return []

        apply_authors = []
        for record in data['history']:
            try:
                author = record['author']
            except KeyError:
                continue
            else:
                self.backend.collect_author(author)
                apply_authors.insert(0, author)

        def _find_change(stream):
            stream = iter(stream)
            author = apply_authors.pop()
            tag = self.backend.generate_avatar(
                    author,
                    'ticket-comment-history',
                    self.ticket_comment_history_size)
            return itertools.chain([next(stream)], tag, stream)

        xpath = '//table[@id="fieldhist"]//td[@class="author"]'
        return [Transformer(xpath).filter(_find_change)]

    def _timeline_filter(self, context):
        data = context['data']
        if 'events' not in data:
            return []

        apply_authors = []
        for event in reversed(data['events']):
            author = event['author']
            self.backend.collect_author(author)
            apply_authors.append(author)

        def find_change(stream):
            stream = iter(stream)
            author = apply_authors.pop()
            tag = self.backend.generate_avatar(
                        author,
                        'timeline',
                        self.timeline_size)
            return itertools.chain(tag, stream)

        xpath = '//div[@id="content"]/dl/dt/a/span[@class="time"]'
        return [Transformer(xpath).filter(find_change)]

    def _wiki_filter(self, context):
        query = context.get('query', '')
        filter_ = []
        if 'action=diff' in query:
            filter_.extend(self._wiki_diff_filter(context))
        elif 'action=history' in query:
            filter_.extend(self._wiki_history_filter(context))
        elif 'version' in query:
            filter_.extend(self._wiki_version_filter(context))

        return filter_

    def _wiki_diff_filter(self, context):
        data = context['data']

        author = data['change']['author']
        self.backend.collect_author(author)
        xpath = '//dd[@class="author"]'
        return [lambda stream: Transformer(xpath).prepend(
                self.backend.generate_avatar(
                        author,
                        'wiki-diff',
                        self.wiki_diff_size))(stream),
        ]

    def _wiki_history_filter(self, context):
        data = context['data']

        def _find_change(stream):
            author = ''.join(stream_part[1] for stream_part in stream if stream_part[0] == 'TEXT').strip()
            tag = self.backend.generate_avatar(
                    author,
                    'wiki-history',
                    self.wiki_history_size)
            return itertools.chain([stream[0]], tag, stream[1:])

        xpath = '//td[@class="author"]'
        return [Transformer(xpath).filter(_find_change)]

    def _wiki_version_filter(self, context):
        data = context['data']

        if 'page' not in data:
            return []

        author = data['page'].author
        xpath = '//table[@id="info"]//th'
        return [lambda stream: Transformer(xpath).prepend(
                self.backend.generate_avatar(
                    author,
                    'wiki-version',
                    self.wiki_version_size))(stream),
        ]

    def _attachment_filter(self, context):
        data = context['data']
        if not data.get('attachment'):
            return []

        author = data['attachment'].author
        if not author:
            return []

        xpath = '//table[@id="info"]//th'
        return [Transformer(xpath).prepend(
                self.backend.generate_avatar(
                            author,
                            'attachment-view',
                            self.attachment_view_size)),
        ]

    def _page_attachments_filter(self, context):
        data = context['data']

        def _find_change(stream):
            author = ''.join(stream_part[1] for stream_part in stream if stream_part[0] == 'TEXT').strip()
            tag = self.backend.generate_avatar(
                    author,
                    'attachment-lineitem',
                    self.attachment_lineitem_size)
            return itertools.chain([stream[0]], tag, stream[1:])

        xpath  = '//div[@id="attachments"]/div/ul/li/span[@class="trac-author-user" or @class="trac-author"]'
        xpath += '|//div[@id="attachments"]/div[@class="attachments"]/dl[@class="attachments"]/dt/span[@class="trac-author-user" or @class="trac-author"]'
        return [Transformer(xpath).filter(_find_change)]

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
                        ia = InitialAvatar(sid)

                        req.send(ia.create(self.AVATAR_WIDTH, self.AVATAR_HEIGHT), 'image/svg+xml')
                        return

        sa = SilhouetteAvatar(email_hash)
        req.send(sa.create(self.AVATAR_WIDTH, self.AVATAR_HEIGHT), 'image/svg+xml')

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield ('avatar', _('Avatar'))

    def render_preference_panel(self, req, panel):
        author = get_reporter_id(req, 'author')

        if req.method == 'POST':
            if 'user_profile_avatar_initialize' in req.args:
                if 'avatar' in req.session:
                    del req.session['avatar']

                req.redirect(req.href.prefs(panel or None))
                return

            if 'user_profile_avatar' in req.args:
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
