#!/usr/bin/python2.5
# Copyright 2010 Google Inc.
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

"""Resources are blobs in the datastore that can contain pages of HTML,
stylesheets, images, or templates.  A Resource is just like a small file
except for a few additional features:
    1. Resources are grouped under ResourceBundles.
    2. Resources can be fetched from the datastore or from files on disk.
    3. We can store localized variants of a resource and select one.
    4. We support compiling and rendering a resource as a Django template.
    5. We cache the fetched, compiled, or rendered result in RAM.
Similar to App Engine's app versions, there is a concept of an "active bundle"
from which resources are obtained.  Previewing or releasing a new set of
resources is a matter of setting the active bundle."""

import django_setup

import datetime
import os
import utils

from google.appengine.ext import db
from google.appengine.ext import webapp


# Requests for files and pages pass through three stages:
#   1. get_rendered(): decides whether to serve plain data or render a Template
#   2. get_localized(): selects the localized variant of a Resource
#   3. Resource.get(): gets a Resource from the datastore or from a file
#
# When a request is served by a dynamic handler, the handler prepares some
# template variables and then renders the template using the same four stages.
#
# Suppose that a static image file '/global/logo.jpg' is requested, the current
# language is 'ru', and there is a Resource entity with key name 'logo.jpg' in
# ResourceBundle '1'.  The expected sequence of calls is as follows:
#
# request for static image, action='logo.jpg'
# > get_rendered('logo.jpg', 'ru')
#   > get_localized('logo.jpg', 'ru')
#     > Resource.get('logo.jpg:ru', B)  # B is <ResourceBundle '1'>
#       > Resource.get_by_key_name('logo.jpg:ru', B) -> None
#       > Resource.load_from_file('logo.jpg:ru') -> None
#     > Resource.get('logo.jpg', B)
#       > Resource.get_by_key_name('logo.jpg', B) -> R1
#     > LOCALIZED_CACHE.put(('logo.jpg', 'ru'), R1)
#   > RENDERED_CACHE.put(('logo.jpg', 'ru', None), R1.content)
# > self.response.out.write(R1.content)
#
# Suppose that a static page '/global/faq.html' is requested.  Assume there is
# a localized 'faq.html.template:ru' resource in Russian and a non-localized
# template file at 'resources/base.template', and all the caches are initially
# empty.  Due to the settings in django_setup.py, resources.TemplateLoader will
# handle template loading.  The expected sequence of calls is as follows:
#
# request for static page, action='faq.html'
# > get_rendered('faq.html', 'ru')
#   > get_localized('faq.html', 'ru')
#     > Resource.get('faq.html:ru') -> None
#     > Resource.get('faq.html') -> None
#   > get_localized('faq.html.template', 'ru')
#     > Resource.get('faq.html.template:ru')
#       > Resource.get_by_key_name('faq.html.template:ru', B) -> R2
#     > LOCALIZED_CACHE.put(('faq.html.template', 'ru'), R2)
#   > R2.get_template() -> T2  # compile the template
#   > T2.render(vars)  # T2 extends "base.html.template", so:
#     > TemplateLoader.load_template('base.html.template')
#       > get_localized('base.html.template', 'ru')
#         > Resource.get('base.html.template:ru')
#           > Resource.get_by_key_name('base.html.template:ru', B) -> None
#           > Resource.load_from_file('base.html.template:ru') -> None
#         > Resource.get('base.html.template')
#           > Resource.get_by_key_name('base.html.template', B) -> None
#           > Resource.load_from_file('base.html.template') -> R3
#         > LOCALIZED_CACHE.put(('base.html.template', 'ru'), R3)
#       > R3.get_template() -> T3  # compile the template
#     > return rendered_string
#   > RENDERED_CACHE.put(('faq.html', 'ru', None), rendered_string)
# > self.response.out.write(rendered_string)
#
# Suppose the dynamic page '/<repo>/view' is now requested.  Assume that R3
# is still cached from the above request.  The expected sequence of calls is:
# 
# request for dynamic page, action='view', with an 'id' query parameter
# > view.Handler.get()
#   > model.Person.get_by_key_name(person_record_id)
#   > BaseHandler.render('view.html', first_name=..., ...)
#     > get_rendered('view.html', 'ru', ..., first_name=..., ...)
#       > get_localized('view.html', 'ru') -> None
#       > get_localized('view.html.template', 'ru')
#         > Resource.get('view.html.template:ru', B)
#           > Resource.get_by_key_name('view.html.template:ru', B) -> None
#           > Resource.load_from_file('view.html.template:ru') -> None
#         > Resource.get('view.html.template')
#           > Resource.get_by_key_name('view.html.template', B) -> None
#           > Resource.load_from_file('view.html.template') -> R4
#         > LOCALIZED_CACHE.put(('view.template', 'ru'), R4)
#       > R4.get_template() -> T4  # compiled the template
#       > T4.render(first_name=..., ...)  # T4 extends "base.html.template", so:
#         > TemplateLoader.load_template('base.html.template')
#           > get_localized('base.html.template', 'ru')
#             > LOCALIZED_CACHE.get(('base.html.template', 'ru')) -> R3
#           > R3.get_template() -> T3  # gets previously compiled R3.template
#         > return rendered_string
#       > return rendered_string  # don't cache
#     > self.response.out.write(rendered_string)


def delta_to_seconds(td):
    """Converts a timedelta to a number of seconds."""
    return td.days*24*3600 + td.seconds + td.microseconds/1e6


class RamCache:
    def __init__(self):
        self.cache = {}

    def clear(self):
        self.cache.clear()

    def put(self, key, value, cache_seconds):
        if cache_seconds > 0:
            expiry = utils.get_utcnow() + datetime.timedelta(0, cache_seconds)
            self.cache[key] = (value, expiry)

    def get(self, key):
        """Gets an item if it's still fresh and returns the item together with
        its remaining cache lifetime in seconds; otherwise returns (None, 0)."""
        if key in self.cache:
            value, expiry = self.cache[key]
            ttl_seconds = delta_to_seconds(expiry - utils.get_utcnow())
            if ttl_seconds > 0:
                return value, ttl_seconds
        return None, 0


class ResourceBundle(db.Model):
    """Parent entity for a set of resources.  The key_name is a bundle name
    arbitrarily chosen by the admin user who stored the resources."""
    created = db.DateTimeProperty(auto_now_add=True)  # for bookkeeping

    def list_resources(self):
        """Returns a list of the names of resources in this bundle."""
        query = Resource.all(keys_only=True).ancestor(self)
        return sorted(key.name() for key in query)


class Resource(db.Model):
    """Resources are blobs in the datastore that can contain pages of HTML,
    stylesheets, images, or templates.  A Resource is just like a small file
    except for a few additional features:
        1. Resources are grouped under ResourceBundles.
        2. Resources can be fetched from the datastore or from files on disk.
        3. We can store localized variants of a resource and select one.
        4. We support compiling and rendering a resource as a Django template.
        5. We cache the fetched, compiled, or rendered result in RAM.
    The key_name is a resource_name or resource_name + ':' + language_code.
    Every Resource entity should be a child of a ResourceBundle."""
    cache_seconds = db.FloatProperty(default=1.0)  # cache TTL of resource
    content = db.BlobProperty()  # binary data or UTF8-encoded template text
    last_modified = db.DateTimeProperty(auto_now=True)  # for bookkeeping

    RESOURCE_DIR = 'resources'  # directory containing resource files
    FILE_CACHE_SECONDS = 30  # length of time to cache files loaded from disk

    @staticmethod
    def load_from_file(name):
        """Creates a Resource from a file, or returns None if no such file."""
        try:
            file = open(Resource.RESOURCE_DIR + '/' + name)
            return Resource(key_name=name, content=file.read(),
                            cache_seconds=float(Resource.FILE_CACHE_SECONDS))
        except IOError:
            return None

    @staticmethod
    def get(name, bundle_name=None):
        """Fetches a resource, first looking in the datastore, then falling
        back to a file on disk.  Returns None if neither is found."""
        parent = bundle_name and db.Key.from_path('ResourceBundle', bundle_name)
        return (parent and Resource.get_by_key_name(name, parent=parent) or
                Resource.load_from_file(name))

    def get_template(self):
        """Compiles the content of this resource into a Template object."""
        if not hasattr(self, 'template'):
            self.template = webapp.template.Template(
                self.content.decode('utf-8'), 'Resource', self.key().name())
        return self.template


LOCALIZED_CACHE = RamCache()  # contains Resource objects
RENDERED_CACHE = RamCache()  # contains strings of rendered content

def clear_caches():
    LOCALIZED_CACHE.clear()
    RENDERED_CACHE.clear()

active_bundle_name = '1'

def set_active_bundle_name(name):
    """Sets the currently active bundle.  Unfortunately, this is a global
    setting because the Django template loader (django_setup.TemplateLoader)
    is also a global setting, and so far we don't know a way to pass the bundle
    name from get_rendered to the template loader."""
    global active_bundle_name
    active_bundle_name = name

def get_localized(name, lang, bundle_name=None):
    """Gets the localized or generic version of a Resource from the cache, the
    datastore, or a file; returns (resource, ttl_seconds) where ttl_seconds is
    its remaining cache lifetime, or (None, 0) if no match is found."""
    bundle_name = bundle_name or active_bundle_name
    cache_key = (bundle_name, name, lang)
    resource, ttl_seconds = LOCALIZED_CACHE.get(cache_key)
    if not resource:
        if lang:
            resource = Resource.get(name + ':' + lang, bundle_name)
        if not resource:
            resource = Resource.get(name, bundle_name)
        if resource:
            ttl_seconds = resource.cache_seconds
            LOCALIZED_CACHE.put(cache_key, resource, ttl_seconds)
    return resource, ttl_seconds

def get_rendered(name, lang, bundle_name=None, extra_key=None,
                 get_vars=lambda: {}, cache_seconds_override=None):
    """Gets rendered or static content from the cache or datastore and returns
    (content, ttl_seconds), where ttl_seconds is the remaining cache lifetime,
    or (None, 0) if nothing suitable is found.  If resource_name is 'foo.html',
    we look for a Resource named 'foo.html' to serve directly, then a Resource
    named 'foo.html.template' to render as a template.  When we need to render
    a template, we call get_vars() to get a dictionary of template variables
    and cache the rendered result with a lifetime set by cache_seconds_override
    (if given) or the Resource's cache_seconds property.  The cache of rendered
    results is keyed on resource_name, lang, and extra_key; use extra_key to
    capture dependencies on template variables."""
    bundle_name = bundle_name or active_bundle_name
    cache_key = (bundle_name, name, lang, extra_key)
    content, ttl_seconds = RENDERED_CACHE.get(cache_key)
    if content is None:
        resource, ttl_seconds = get_localized(name, lang, bundle_name)
        if resource:  # a plain file is available
            return resource.content, ttl_seconds
        resource, ttl_seconds = get_localized(name + '.template', lang, bundle_name)
        if resource:  # a template is available
            content = render_in_lang(resource.get_template(), lang, get_vars())
            if cache_seconds_override is not None:
                ttl_seconds = cache_seconds_override
            RENDERED_CACHE.put(cache_key, content, ttl_seconds)
    return content, ttl_seconds

def render_in_lang(template, lang, vars):
    """Renders a template in a given language.  We use this to ensure that
    Django's idea of the current language matches our cache keys."""
    import django.utils.translation
    original_lang = django.utils.translation.get_language()
    try:
        django.utils.translation.activate(lang)
        return template.render(webapp.template.Context(vars))
    finally:
        django.utils.translation.activate(original_lang)
