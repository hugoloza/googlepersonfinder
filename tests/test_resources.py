#!/usr/bin/python2.5
# encoding: utf-8
# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for resources.py."""

import unittest

from google.appengine.ext import db
from google.appengine.ext import webapp
import resources
from resources import Resource, ResourceBundle
import utils
import sys


class RamCacheTests(unittest.TestCase):
    def setUp(self):
        utils.set_utcnow_for_test(0)

    def tearDown(self):
        utils.set_utcnow_for_test(None)

    def test_data_is_cached(self):
        cache = resources.RamCache()
        cache.put('a', 'b', 1)
        assert cache.get('a') == ('b', 1)

    def test_ttl_zero_not_cached(self):
        cache = resources.RamCache()
        cache.put('a', 'b', 0)
        assert cache.get('a') == (None, 0)

    def test_data_expires_after_ttl(self):
        cache = resources.RamCache()
        cache.put('a', 'b', 10)
        utils.set_utcnow_for_test(9)
        assert cache.get('a') == ('b', 1)
        utils.set_utcnow_for_test(11)
        assert cache.get('a') == (None, 0)

    def test_clear(self):
        cache = resources.RamCache()
        cache.put('a', 'b', 1)
        assert cache.get('a') == ('b', 1)
        cache.clear()
        assert cache.get('a') == (None, 0)


class ResourcesTests(unittest.TestCase):
    def setUp(self):
        utils.set_utcnow_for_test(0)
        resources.clear_caches()
        resources.set_active_bundle_name('1')

        self.temp_entity_keys = []
        self.put_resource('1', 'base.html.template', 50,
                          'hi! {% block foo %}{% endblock foo %}')
        self.put_resource('1', 'base.html.template:es', 40,
                          '\xc2\xa1hola! {% block foo %}{% endblock foo %}')
        self.put_resource('1', 'page.html.template', 30,
                          '{% extends "base.html.template" %} '
                          '{% block foo %}default{% endblock foo %}')
        self.put_resource('1', 'page.html.template:fr', 20,
                          '{% extends "base.html.template" %} '
                          '{% block foo %}fran\xc3\xa7ais{% endblock foo %}')
        self.put_resource('1', 'static.html', 30, 'hello')
        self.put_resource('1', 'static.html:fr', 20, 'bonjour')
        self.put_resource('1', 'data', 10, '\xff\xfe\xfd\xfc')

        self.fetched = []
        self.compiled = []
        self.rendered = []

        self.resource_get_by_key_name_original = Resource.get_by_key_name
        self.template_init_original = webapp.template.Template.__init__
        self.template_render_original = webapp.template.Template.render

        test_self = self

        @staticmethod
        def resource_get_by_key_name_for_test(key_name, parent):
            test_self.fetched.append(key_name)  # track datastore fetches
            return test_self.resource_get_by_key_name_original(key_name, parent)

        def template_init_for_test(self, content, origin, name):
            test_self.compiled.append(name)  # track template compilations
            return test_self.template_init_original(self, content, origin, name)

        def template_render_for_test(self, context):
            test_self.rendered.append(self.name)  # track render calls
            return test_self.template_render_original(self, context)

        Resource.get_by_key_name = resource_get_by_key_name_for_test
        webapp.template.Template.__init__ = template_init_for_test
        webapp.template.Template.render = template_render_for_test

    def tearDown(self):
        utils.set_utcnow_for_test(None)
        resources.clear_caches()

        Resource.get_by_key_name = self.resource_get_by_key_name_original
        webapp.template.Template.__init__ = self.template_init_original
        webapp.template.Template.render = self.template_render_original

        db.delete(self.temp_entity_keys)

    def put_resource(self, bundle_name, name, cache_seconds, content):
        """Puts a Resource in the datastore for testing, and tracks it to
        be cleaned up in test teardown."""
        bundle = ResourceBundle(key_name=bundle_name)
        key = Resource(parent=bundle, key_name=name, content=content,
                       cache_seconds=float(cache_seconds)).put()
        self.temp_entity_keys.append(key)

    def delete_resource(self, bundle_name, name):
        """Deletes a Resource that was put by put_resource."""
        key = db.Key.from_path('ResourceBundle', bundle_name, 'Resource', name)
        db.delete(key)
        self.temp_entity_keys.remove(key)

    def check_get_localized(self, name, lang, expected_content, expected_ttl):
        resource, ttl_seconds = resources.get_localized(name, lang)
        assert resource.content == expected_content, 'actual: %r, expected: %r' % (resource.content, expected_content)
        assert ttl_seconds == expected_ttl, 'actual: %r, expected: %r' % (ttl_seconds, expected_ttl)

    def test_get(self):
        # Verify that Resource.get fetches a Resource from the datastore.
        assert Resource.get('xyz', '1') is None
        self.put_resource('1', 'xyz', 10, 'pqr')
        assert Resource.get('xyz', '1').content == 'pqr'
        self.delete_resource('1', 'xyz')
        assert Resource.get('xyz', '1') is None

        # Verify that Resource.get fetches a Resource from an existing file.
        content = Resource.get('message.html.template', '1').content
        assert content != 'pqr'

        # Verify that the file can be overriden by a datastore entity.
        self.put_resource('1', 'message.html.template', 10, 'pqr')
        assert Resource.get('message.html.template', '1').content == 'pqr'
        self.delete_resource('1', 'message.html.template')
        assert Resource.get('message.html.template', '1').content == content

    def test_set_active_bundle_name(self):
        # Verifies that get_localized and get_rendered are properly affected
        # by set_active_bundle_name.
        self.put_resource('1', 'xyz', 0, 'one')
        self.put_resource('2', 'xyz', 0, 'two')
        self.check_get_localized('xyz', 'en', 'one', 0)
        assert resources.get_rendered('xyz', 'en') == ('one', 0)
        resources.set_active_bundle_name('2')
        self.check_get_localized('xyz', 'en', 'two', 0)
        assert resources.get_rendered('xyz', 'en') == ('two', 0)
        resources.set_active_bundle_name('1')
        self.check_get_localized('xyz', 'en', 'one', 0)
        assert resources.get_rendered('xyz', 'en') == ('one', 0)

    def test_get_localized(self):
        # These three fetches should load resources into the cache.
        self.fetched = []
        self.check_get_localized('static.html', 'es', 'hello', 30)
        assert self.fetched == ['static.html:es', 'static.html']
        self.fetched = []
        self.check_get_localized('static.html', 'en', 'hello', 30)
        assert self.fetched == ['static.html:en', 'static.html']
        self.fetched = []
        self.check_get_localized('static.html', 'fr', 'bonjour', 20)
        assert self.fetched == ['static.html:fr']

        # These should be cache hits, and shouldn't touch the datastore.
        utils.set_utcnow_for_test(1)
        self.fetched = []
        self.check_get_localized('static.html', 'es', 'hello', 29)
        self.check_get_localized('static.html', 'en', 'hello', 29)
        self.check_get_localized('static.html', 'fr', 'bonjour', 19)
        assert self.fetched == []

        # Expire static.html:fr from the cache.
        utils.set_utcnow_for_test(21)
        self.fetched = []
        self.check_get_localized('static.html', 'es', 'hello', 9)
        self.check_get_localized('static.html', 'en', 'hello', 9)
        assert self.fetched == []
        self.check_get_localized('static.html', 'fr', 'bonjour', 20)
        assert self.fetched == ['static.html:fr']

        # Expire static.html:es from the cache (static.html:fr remains cached).
        utils.set_utcnow_for_test(31)
        self.fetched = []
        self.check_get_localized('static.html', 'es', 'hello', 30)
        assert self.fetched == ['static.html:es', 'static.html']
        self.fetched = []
        self.check_get_localized('static.html', 'en', 'hello', 30)
        assert self.fetched == ['static.html:en', 'static.html']
        self.fetched = []
        self.check_get_localized('static.html', 'fr', 'bonjour', 10)
        assert self.fetched == []

    def test_get_rendered(self):
        get_rendered = resources.get_rendered
        eq = self.assertEquals

        # There's no es-specific page but there is an es-specific base template.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'es') == (u'\xa1hola! default', 30)
        assert self.fetched == ['page.html:es', 'page.html',
                                'page.html.template:es', 'page.html.template',
                                'base.html.template:es']
        assert self.compiled == ['page.html.template', 'base.html.template:es']
        assert self.rendered == ['page.html.template']

        # There's an fr-specific page but no fr-specific base template.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'fr') == (u'hi! fran\xe7ais', 20)
        assert self.fetched == ['page.html:fr', 'page.html',
                                'page.html.template:fr',
                                'base.html.template:fr', 'base.html.template']
        assert self.compiled == ['page.html.template:fr', 'base.html.template']
        assert self.rendered == ['page.html.template:fr']

        # There's no en-specific page and no en-specific base template.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'en') == (u'hi! default', 30)
        assert self.fetched == ['page.html:en', 'page.html',
                                'page.html.template:en', 'page.html.template',
                                'base.html.template:en', 'base.html.template']
        assert self.compiled == ['page.html.template', 'base.html.template']
        assert self.rendered == ['page.html.template']

        # These should be cache hits, and shouldn't fetch, compile, or render.
        utils.set_utcnow_for_test(1)
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'es') == (u'\xa1hola! default', 29)
        assert get_rendered('page.html', 'fr') == (u'hi! fran\xe7ais', 19)
        assert get_rendered('page.html', 'en') == (u'hi! default', 29)
        assert self.fetched == []
        assert self.compiled == []
        assert self.rendered == []

        # Expire the pages but not the base templates.
        utils.set_utcnow_for_test(31)

        # Should fetch and recompile the pages but not the base templates.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'es') == (u'\xa1hola! default', 30)
        assert self.fetched == ['page.html:es', 'page.html',
                                'page.html.template:es', 'page.html.template']
        assert self.compiled == ['page.html.template']
        assert self.rendered == ['page.html.template']

        # Should fetch and recompile the pages but not the base templates.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'fr') == (u'hi! fran\xe7ais', 20)
        assert self.fetched == ['page.html:fr', 'page.html',
                                'page.html.template:fr']
        assert self.compiled == ['page.html.template:fr']
        assert self.rendered == ['page.html.template:fr']

        # Should fetch and recompile the pages but not the base templates.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'en') == (u'hi! default', 30)
        assert self.fetched == ['page.html:en', 'page.html',
                                'page.html.template:en', 'page.html.template']
        assert self.compiled == ['page.html.template']
        assert self.rendered == ['page.html.template']

        # Expire the base templates and page.html.template:fr
        # (page.html.template:en and page.html.template:es remain cached).
        utils.set_utcnow_for_test(52)

        # Should fetch nothing, since the page is still cached.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'es') == \
            (u'\xa1hola! default', 31 + 30 - 52)
        assert self.fetched == []
        assert self.compiled == []
        assert self.rendered == []

        # Should fetch and recompile both the fr page and the base template.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'fr') == (u'hi! fran\xe7ais', 20)
        assert self.fetched == ['page.html:fr', 'page.html',
                                'page.html.template:fr',
                                'base.html.template:fr', 'base.html.template']
        assert self.compiled == ['page.html.template:fr', 'base.html.template']
        assert self.rendered == ['page.html.template:fr']

        # Should fetch nothing, since the page is still cached.
        self.fetched, self.compiled, self.rendered = [], [], []
        assert get_rendered('page.html', 'en') == \
            (u'hi! default', 31 + 30 - 52)
        assert self.fetched == []
        assert self.compiled == []
        assert self.rendered == []

        # Ensure binary data is preserved.
        assert get_rendered('data', 'en') == ('\xff\xfe\xfd\xfc', 10)

