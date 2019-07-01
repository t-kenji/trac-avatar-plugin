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
import re
import hashlib
import itertools

from trac.core import *
from trac.config import Option
from genshi.builder import tag

class AvatarBackend():
    
    default = Option('avatar', 'avatar_default', default='default',
                     doc="The default value to pass along to avatar to "
                         "use if the email address does not match.")
    backend = Option('avatar', 'backend', default='built-in',
                     doc="The name of the avatar service to use as a "
                         "backend.  Currently built-in, gravatar, libravatar "
                         "and custom are supported.")
    custom_backend = Option('avatar', 'custom_backend', default='',
                            doc="The URL of the avator service to use as a "
                                "custom backend.")

    # A mapping of possible backends to their peculiarities
    external_backends = {
        'gravatar': {
            'url': 'gravatar.com',
            'base': 'http://www.gravatar.com/avatar/',
            'base_ssl': 'https://gravatar.com/avatar/',
        },
        'libravatar': {
            'url': 'libravatar.org',
            'base': 'http://cdn.libravatar.org/avatar/',
            'base_ssl': 'https://seccdn.libravatar.org/avatar/',
        },
    }

    backends = {}

    # from trac source
    _long_author_re = re.compile(r'.*<([^@]+)@([^@]+)>\s*|([^@]+)@([^@]+)')

    def __init__(self, env, config):
        self.env = env
        self.config = config
        self.author_data = {}

        abs_href = self.env.abs_href()
	if not abs_href.startswith('http'):
	    # maybe called by trac-admin command.
	    return

        self.is_https =  abs_href.startswith('https://')
        match = re.match(r'https?://(?P<domain>[\w\d\.\-_\:]+)(?P<subdirectory>/[\w\d\.\-_/]*)?', abs_href)
        if match.lastgroup == 'subdirectory':
            self.backends.update({'built-in': {
                'url': '{}{}'.format(match.group('domain'), match.group('subdirectory')),
                'base': 'http://{}{}/avatar/'.format(match.group('domain'), match.group('subdirectory')),
                'base_ssl': 'https://{}{}/avatar/'.format(match.group('domain'), match.group('subdirectory')),
            }})
        else:
            self.backends.update({'built-in': {
                'url': '{}'.format(match.group('domain')),
                'base': 'http://{}/avatar/'.format(match.group('domain')),
                'base_ssl': 'https://{}/avatar/'.format(match.group('domain')),
            }})

        self.backends.update({'custom': {
            'url': 'custom',
            'base': self.custom_backend,
            'base_ssl': self.custom_backend,
        }})
        self.backends.update(self.external_backends)

    def get_backend(self):
        return self.backends[self.backend]

    def collect_author(self, author):
        if author and not self.author_data.get(author, None):
            self.author_data[author] = None

    def lookup_author_data(self):
        author_names = [a for a in self.author_data if a]
        lookup_authors = sorted([a for a in author_names if '@' not in a])
        email_authors = set(author_names).difference(lookup_authors)

        if lookup_authors:
            for sid, email in self.env.db_query("""
                    SELECT sid, value FROM session_attribute
                    WHERE name=%%s AND sid IN (%s)
                    """ % ','.join(['%s'] * len(lookup_authors)),
                    ('email',) + tuple(lookup_authors)):
                self.author_data[sid] = self._avatar_slug(email)

        for author in email_authors:
            author_info = self._long_author_re.match(author)
            if author_info:
                if author_info.group(1):
                    name, host = author_info.group(1, 2)
                elif author_info.group(3):
                    name, host = author_info.group(3, 4)
                else:
                    continue
                self.author_data[name] = \
                    self.author_data[author] = \
                    self._avatar_slug('%s@%s' % (name, host))

    def clear_auth_data(self):
        self.author_data.clear()

    def generate_avatar(self, author, class_, size):
        if author is None or len(author) == 0:
            return tag.span()
        email_hash = self.author_data.get(author, None) or self._avatar_slug(author)
        if self.is_https:
            href = self.backends[self.backend]['base_ssl'] + email_hash
        else:
            href = self.backends[self.backend]['base'] + email_hash

        # for some reason sizing doesn't work if you pass "default=default"
        if self.default != 'default':
            href += "&default=%s" % (self.default,)
        return tag.img(src=href, class_='avatar %s' % class_, width=size, height=size).generate()

    def _avatar_slug(self, email):
        if email is None:
            email = ''
        if isinstance(email, unicode):
            email = email.encode('utf-8')
        return hashlib.md5(email.lower()).hexdigest()
