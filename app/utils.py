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

__author__ = 'kpy@google.com (Ka-Ping Yee) and many other Googlers'

import cgi
from datetime import datetime, timedelta
import httplib
import logging
import model
import os
import pfif
import random
import re
import time
import traceback
import urllib
import urlparse

from google.appengine.dist import use_library
use_library('django', '1.1')

import django.conf
import django.utils.html
from google.appengine.api import images
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import webapp
import google.appengine.ext.webapp.template
import google.appengine.ext.webapp.util
from recaptcha.client import captcha

import config

if os.environ.get('SERVER_SOFTWARE', '').startswith('Development'):
    # See http://code.google.com/p/googleappengine/issues/detail?id=985
    import urllib
    urllib.getproxies_macosx_sysconf = lambda: {}

ROOT = os.path.abspath(os.path.dirname(__file__))


# ==== Localization setup ======================================================

try:
    django.conf.settings.configure()
except:
    pass
django.conf.settings.LANGUAGE_CODE = 'en'
django.conf.settings.USE_I18N = True
django.conf.settings.LOCALE_PATHS = (os.path.join(ROOT, 'locale'),)
django.conf.settings.LANGUAGES_BIDI = ['ar', 'he', 'fa', 'iw', 'ur']

import django.utils.translation
# We use lazy translation in this file because the locale isn't set until the
# Handler is initialized.
from django.utils.translation import gettext_lazy as _

# Mapping from language codes to endonyms for all available languages.
LANGUAGE_ENDONYMS = {
    'ar': u'\u0627\u0644\u0639\u0631\u0628\u064A\u0629',
    'bg': u'\u0431\u044A\u043B\u0433\u0430\u0440\u0441\u043A\u0438',
    'ca': u'Catal\u00E0',
    'cs': u'\u010De\u0161tina',
    'da': u'Dansk',
    'de': u'Deutsch',
    'el': u'\u0395\u03BB\u03BB\u03B7\u03BD\u03B9\u03BA\u03AC',
    'en': u'English',
    'en-GB': u'English (UK)',
    'es': u'espa\u00F1ol',
    'es_419': u'espa\u00F1ol (Latinoam\u00e9rica)',
    'eu': u'Euskara',
    'fa': u'\u0641\u0627\u0631\u0633\u06CC',
    'fi': u'suomi',
    'fil': u'Filipino',
    'fr': u'Fran\u00e7ais',
    'fr-CA': u'Fran\u00e7ais (Canada)',
    'gl': u'Galego',
    'hi': u'\u0939\u093F\u0928\u094D\u0926\u0940',
    'hr': u'Hrvatski',
    'ht': u'Krey\u00f2l',
    'hu': u'magyar',
    'id': u'Bahasa Indonesia',
    'it': u'Italiano',
    'he': u'\u05E2\u05D1\u05E8\u05D9\u05EA',
    'ja': u'\u65E5\u672C\u8A9E',
    'ko': u'\uD55C\uAD6D\uC5B4',
    'lt': u'Lietuvi\u0173',
    'lv': u'Latvie\u0161u valoda',
    'nl': u'Nederlands',
    'no': u'Norsk',
    'pl': u'polski',
    'pt-PT': u'Portugu\u00EAs (Portugal)',
    'pt-BR': u'Portugu\u00EAs (Brasil)',
    'ro': u'Rom\u00E2n\u0103',
    'ru': u'\u0420\u0443\u0441\u0441\u043A\u0438\u0439',
    'sk': u'Sloven\u010Dina',
    'sl': u'Sloven\u0161\u010Dina',
    'sr': u'\u0441\u0440\u043F\u0441\u043A\u0438',
    'sv': u'Svenska',
    'th': u'\u0E44\u0E17\u0E22',
    'tr': u'T\u00FCrk\u00E7e',
    'uk': u'\u0423\u043A\u0440\u0430\u0457\u043D\u0441\u044C\u043A\u0430',
    'ur': u'\u0627\u0631\u062F\u0648',
    'vi': u'Ti\u1EBFng Vi\u1EC7t',
    'zh-TW': u'\u4E2D \u6587 (\u7E41 \u9AD4)',
    'zh-CN': u'\u4E2D \u6587 (\u7B80 \u4F53)',
}

# Mapping from language codes to English names for all available languages.
LANGUAGE_EXONYMS = {
    'ar': 'Arabic',
    'bg': 'Bulgarian',
    'ca': 'Catalan',
    'cs': 'Czech',
    'da': 'Danish',
    'de': 'German',
    'el': 'Greek',
    'en': 'English (US)',
    'en-GB': 'English (UK)',
    'es': 'Spanish',
    'es_419': 'Spanish (Latin America)',
    'eu': 'Basque',
    'fa': 'Persian',
    'fi': 'Finnish',
    'fil': 'Filipino',
    'fr': 'French (France)',
    'fr-CA': 'French (Canada)',
    'gl': 'Galician',
    'hi': 'Hindi',
    'hr': 'Croatian',
    'ht': 'Haitian Creole',
    'hu': 'Hungarian',
    'id': 'Indonesian',
    'it': 'Italian',
    'he': 'Hebrew',
    'ja': 'Japanese',
    'ko': 'Korean',
    'lt': 'Lithuanian',
    'lv': 'Latvian',
    'nl': 'Dutch',
    'no': 'Norwegian',
    'pl': 'Polish',
    'pt-PT': 'Portuguese (Portugal)',
    'pt-BR': 'Portuguese (Brazil)',
    'ro': 'Romanian',
    'ru': 'Russian',
    'sk': 'Slovak',
    'sl': 'Slovenian',
    'sr': 'Serbian',
    'sv': 'Swedish',
    'th': 'Thai',
    'tr': 'Turkish',
    'uk': 'Ukranian',
    'ur': 'Urdu',
    'vi': 'Vietnamese',
    'zh-TW': 'Chinese (Traditional)',
    'zh-CN': 'Chinese (Simplified)',
}

# Mapping from language codes to the names of LayoutCode constants.  See:
# http://code.google.com/apis/ajaxlanguage/documentation/referenceKeyboard.html
VIRTUAL_KEYBOARD_LAYOUTS = {
    'ur': 'URDU'
}


# ==== Field value text ========================================================

# UI text for the sex field when displaying a person.
PERSON_SEX_TEXT = {
    # This dictionary must have an entry for '' that gives the default text.
    '': '',
    'female': _('female'),
    'male': _('male'),
    'other': _('other')
}

assert set(PERSON_SEX_TEXT.keys()) == set(pfif.PERSON_SEX_VALUES)

def get_person_sex_text(person):
    """Returns the UI text for a person's sex field."""
    return PERSON_SEX_TEXT.get(person.sex or '')

# UI text for the status field when posting or displaying a note.
NOTE_STATUS_TEXT = {
    # This dictionary must have an entry for '' that gives the default text.
    '': _('Unspecified'),
    'information_sought': _('I am seeking information'),
    'is_note_author': _('I am this person'),
    'believed_alive':
        _('I have received information that this person is alive'),
    'believed_missing': _('I have reason to think this person is missing'),
    'believed_dead': _('I have received information that this person is dead'),
}

assert set(NOTE_STATUS_TEXT.keys()) == set(pfif.NOTE_STATUS_VALUES)

def get_note_status_text(note):
    """Returns the UI text for a note's status field."""
    return NOTE_STATUS_TEXT.get(note.status or '')


# UI text for the rolled-up status when displaying a person.
PERSON_STATUS_TEXT = {
    # This dictionary must have an entry for '' that gives the default text.
    '': _('Unspecified'),
    'information_sought': _('Someone is seeking information about this person'),
    'is_note_author': _('This person has posted a message'),
    'believed_alive':
        _('Someone has received information that this person is alive'),
    'believed_missing': _('Someone has reported that this person is missing'),
    'believed_dead':
        _('Someone has received information that this person is dead'),
}

assert set(PERSON_STATUS_TEXT.keys()) == set(pfif.NOTE_STATUS_VALUES)

def get_person_status_text(person):
    """Returns the UI text for a person's latest_status."""
    return PERSON_STATUS_TEXT.get(person.latest_status or '')

# ==== String formatting =======================================================

def format_utc_datetime(dt):
    if dt is None:
        return ''
    integer_dt = datetime(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return integer_dt.isoformat() + 'Z'

def format_sitemaps_datetime(dt):
    integer_dt = datetime(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return integer_dt.isoformat() + '+00:00'

def encode(string, encoding='utf-8'):
    """If unicode, encode to encoding; if 8-bit string, leave unchanged."""
    if isinstance(string, unicode):
        string = string.encode(encoding)
    return string

def urlencode(params, encoding='utf-8'):
    """Apply encoding to any Unicode strings in the parameter dict.
    Leave 8-bit strings alone.  (urllib.urlencode doesn't support Unicode.)"""
    keys = params.keys()
    keys.sort()  # Sort the keys to get canonical ordering
    return urllib.urlencode([
        (encode(key, encoding), encode(params[key], encoding))
        for key in keys if isinstance(params[key], basestring)])

def set_url_param(url, param, value):
    """This modifies a URL setting the given param to the specified value.  This
    may add the param or override an existing value, or, if the value is None,
    it will remove the param.  Note that value must be a basestring and can't be
    an int, for example."""
    url_parts = list(urlparse.urlparse(url))
    params = dict(cgi.parse_qsl(url_parts[4]))
    if value is None:
        if param in params:
            del(params[param])
    else:
        params[param] = value
    url_parts[4] = urlencode(params)
    return urlparse.urlunparse(url_parts)

def anchor_start(href):
    """Returns the HREF escaped and embedded in an anchor tag."""
    return '<a href="%s">' % django.utils.html.escape(href)

def anchor(href, body):
    """Returns a string anchor HTML element with the given href and body."""
    return anchor_start(href) + django.utils.html.escape(body) + '</a>'

# ==== Validators ==============================================================

# These validator functions are used to check and parse query parameters.
# When a query parameter is missing or invalid, the validator returns a
# default value.  For parameter types with a false value, the default is the
# false value.  For types with no false value, the default is None.

def strip(string):
    # Trailing nulls appear in some strange character encodings like Shift-JIS.
    return string.strip().rstrip('\0')

def validate_yes(string):
    return (strip(string).lower() == 'yes') and 'yes' or ''

def validate_checkbox(string):
    return (strip(string).lower() == 'on') and 'yes' or ''

def validate_role(string):
    return (strip(string).lower() == 'provide') and 'provide' or 'seek'

def validate_int(string):
    return string and int(strip(string))

def validate_sex(string):
    """Validates the 'sex' parameter, returning a canonical value or ''."""
    if string:
        string = strip(string).lower()
    return string in pfif.PERSON_SEX_VALUES and string or ''

APPROXIMATE_DATE_RE = re.compile(r'^\d{4}(-\d\d)?(-\d\d)?$')

def validate_approximate_date(string):
    if string:
        string = strip(string)
        if APPROXIMATE_DATE_RE.match(string):
            return string
    return ''

AGE_RE = re.compile(r'^\d+(-\d+)?$')

def validate_age(string):
    """Validates the 'age' parameter, returning a canonical value or ''."""
    if string:
        string = strip(string)
        if AGE_RE.match(string):
            return string
    return ''

def validate_status(string):
    """Validates an incoming status parameter, returning one of the canonical
    status strings or ''.  Note that '' is always used as the Python value
    to represent the 'unspecified' status."""
    if string:
        string = strip(string).lower()
    return string in pfif.NOTE_STATUS_VALUES and string or ''

DATETIME_RE = re.compile(r'^(\d\d\d\d)-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)Z$')

def validate_datetime(string):
    if not string:
        return None  # A missing value is okay.
    match = DATETIME_RE.match(string)
    if match:
        return datetime(*map(int, match.groups()))
    raise ValueError('Bad datetime: %r' % string)

def validate_timestamp(string):
    try:
        return string and datetime.utcfromtimestamp(float(strip(string)))
    except:
        raise ValueError('Bad timestamp %s' % string)

def validate_image(bytestring):
    try:
        image = ''
        if bytestring:
            image = images.Image(bytestring)
            image.width
        return image
    except:
        return False

def validate_version(string):
    """Version, if present, should be in pfif versions."""
    if string and strip(string) not in pfif.PFIF_VERSIONS:
        raise ValueError('Bad pfif version: %s' % string)
    return string


# ==== Other utilities =========================================================

def optionally_filter_sensitive_fields(records, auth=None):
    """Removes sensitive fields from a list of dictionaries, unless the client
    has full read authorization."""
    if not (auth and auth.full_read_permission):
        filter_sensitive_fields(records)

def filter_sensitive_fields(records):
    """Removes sensitive fields from a list of dictionaries."""
    for record in records:
        if 'date_of_birth' in record:
            record['date_of_birth'] = ''
        if 'author_email' in record:
            record['author_email'] = ''
        if 'author_phone' in record:
            record['author_phone'] = ''
        if 'email_of_found_person' in record:
            record['email_of_found_person'] = ''
        if 'phone_of_found_person' in record:
            record['phone_of_found_person'] = ''

def get_secret(name):
    """Gets a secret from the datastore by name, or returns None if missing."""
    secret = model.Secret.get_by_key_name(name)
    if secret:
        return secret.secret

# a datetime.datetime object representing debug time.
_utcnow_for_test = None

def set_utcnow_for_test(now):
    """Set current time for debug purposes."""
    global _utcnow_for_test
    _utcnow_for_test = now

def get_utcnow():
    """Return current time in utc, or debug value if set."""
    global _utcnow_for_test
    return _utcnow_for_test or datetime.utcnow()

def get_local_message(local_messages, lang, default_message):
    """Return a localized message for lang where local_messages is a dictionary
    mapping language codes and localized messages, or return default_message if
    no such message is found."""
    if not isinstance(local_messages, dict):
        return default_message
    return local_messages.get(lang, local_messages.get('en', default_message))

def get_full_name(first_name, last_name, config):
    """Return full name string obtained by concatenating first_name and
    last_name in the order specified by config.family_name_first, or just
    first_name if config.use_family_name is False."""
    if config.use_family_name:
        separator = (first_name and last_name) and u' ' or u''
        if config.family_name_first:
            return separator.join([last_name, first_name])
        else:
            return separator.join([first_name, last_name])
    else:
        return first_name

# ==== Base Handler ============================================================

class Struct:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

global_cache = {}
global_cache_insert_time = {}


class Handler(webapp.RequestHandler):
    # Regular expression to detect Japanese Tier-2 mobile phones.
    JP_TIER2_MOBILE_USER_AGENT_RE = re.compile(
        r'^(KDDI|DoCoMo|SoftBank|J-PHONE|Vodafone)')

    # Handlers that don't use a subdomain configuration can set this to False.
    subdomain_required = True

    # Handlers that require HTTPS can set this to True.
    https_required = False

    # Handlers to enable even for deactivated subdomains can set this to True.
    ignore_deactivation = False

    auto_params = {
        'lang': strip,
        'query': strip,
        'first_name': strip,
        'last_name': strip,
        'alternate_first_names': strip,
        'alternate_last_names': strip,
        'sex': validate_sex,
        'date_of_birth': validate_approximate_date,
        'age': validate_age,
        'home_street': strip,
        'home_neighborhood': strip,
        'home_city': strip,
        'home_state': strip,
        'home_postal_code': strip,
        'home_country': strip,
        'author_name': strip,
        'author_phone': strip,
        'author_email': strip,
        'source_url': strip,
        'source_date': strip,
        'source_name': strip,
        'description': strip,
        'dupe_notes': validate_yes,
        'id': strip,
        'text': strip,
        'status': validate_status,
        'last_known_location': strip,
        'found': validate_yes,
        'email_of_found_person': strip,
        'phone_of_found_person': strip,
        'error': strip,
        'role': validate_role,
        'clone': validate_yes,
        'small': validate_yes,
        'style': strip,
        'add_note': validate_yes,
        'photo_url': strip,
        'photo': validate_image,
        'max_results': validate_int,
        'skip': validate_int,
        'min_entry_date': validate_datetime,
        'person_record_id': strip,
        'omit_notes': validate_yes,
        'id1': strip,
        'id2': strip,
        'id3': strip,
        'version': validate_version,
        'content_id': strip,
        'target': strip,
        'signature': strip,
        'flush_cache': validate_yes,
        'operation': strip,
        'confirm': validate_yes,
        'key': strip,
        'subdomain_new': strip,
        'utcnow': validate_timestamp,
        'subscribe_email' : strip,
        'subscribe' : validate_checkbox,
        'redirect' : validate_int,
    }

    def get_mobile_spec(self):
        """Retruns 'tier2' if the request is from Japanese Tier-2 mobile phone.
        Returns empty string if not."""
        user_agent = self.request.headers.get('User-Agent')
        if user_agent and self.JP_TIER2_MOBILE_USER_AGENT_RE.match(user_agent):
            return 'tier2'
        return ''

    def maybe_redirect_jp_tier2_mobile(self):
        # If this is an access from Japanese Tier-2 phone,
        # returns URL to redirect it to sagasu-m.appspot.com .
        if (self.config and
            self.config.jp_tier2_mobile_redirect_url and
            self.params.redirect != 0 and
            self.params.small != 'yes' and
            self.get_mobile_spec() == 'tier2'):
            # Except for top page, we propagate path and query params.
            redirect_url = (self.config.jp_tier2_mobile_redirect_url +
                            self.request.path)
            if self.request.path != '/' and self.request.query_string:
                redirect_url += '?' + self.request.query_string
            return redirect_url
        return ''

    def redirect(self, url, **params):
        if re.match('^[a-z]+:', url):
            if params:
                url += '?' + urlencode(params, self.charset)
        else:
            url = self.get_url(url, **params)
        return webapp.RequestHandler.redirect(self, url)

    def cache_key_for_request(self):
        # Use the whole URL as the key, ensuring that lang is included.
        # We must use the computed lang (self.env.lang), not the query
        # parameter (self.params.lang).
        url = set_url_param(self.request.url, 'lang', self.env.lang)

        # Include the charset in the key, since the <meta> tag can differ.
        return set_url_param(url, 'charsets', self.charset)

    def render_from_cache(self, cache_time, key=None):
        """Render from cache if appropriate. Returns true if done."""
        if not cache_time:
            return False

        now = time.time()
        key = self.cache_key_for_request()
        if cache_time > (now - global_cache_insert_time.get(key, 0)):
            self.write(global_cache[key])
            logging.debug('Rendering cached response.')
            return True
        logging.debug('Render cache missing/stale, re-rendering.')
        return False

    def render(self, name, cache_time=0, **values):
        """Renders the template, optionally caching locally.

        The optional cache is local instead of memcache--this is faster but
        will be recomputed for every running instance.  It also consumes local
        memory, but that's not a likely issue for likely amounts of cached data.

        Args:
            name: name of the file in the template directory.
            cache_time: optional time in seconds to cache the response locally.
        """
        if self.render_from_cache(cache_time):
            return
        values['env'] = self.env  # pass along application-wide context
        values['params'] = self.params  # pass along the query parameters
        values['config'] = self.config  # pass along the configuration
        # TODO(kpy): Remove "templates/" from all template names in calls
        # to this method, and have this method call render_to_string instead.
        response = webapp.template.render(os.path.join(ROOT, name), values)
        self.write(response)
        if cache_time:
            now = time.time()
            key = self.cache_key_for_request()
            global_cache[key] = response
            global_cache_insert_time[key] = now

    def render_to_string(self, name, **values):
        """Renders the specified template to a string."""
        return webapp.template.render(
            os.path.join(ROOT, 'templates', name), values)

    def error(self, code, message=''):
        self.info(code, message, style='error')

    def info(self, code, message='', message_html='', style='info'):
        is_error = 400 <= code < 600
        if is_error:
            webapp.RequestHandler.error(self, code)
        else:
            self.response.set_status(code)
        if not message and not message_html:
            message = '%d: %s' % (code, httplib.responses.get(code))
        try:
            self.render('templates/message.html', cls=style,
                        message=message, message_html=message_html)
        except:
            self.response.out.write(message)
        self.terminate_response()

    def terminate_response(self):
        """Prevents any further output from being written."""
        self.response.out.write = lambda *args: None
        self.get = lambda *args: None
        self.post = lambda *args: None

    def write(self, text):
        """Sends text to the client using the charset from initialize()."""
        self.response.out.write(text.encode(self.charset, 'replace'))

    def select_charset(self):
        # Get a list of the charsets that the client supports.
        if self.request.get('charsets'): # allow override for testing
            charsets = self.request.get('charsets').split(',')
        else:
            charsets = self.request.accept_charset.best_matches()

        # Always prefer UTF-8 if the client supports it.
        for charset in charsets:
            if charset.lower().replace('_', '-') in ['utf8', 'utf-8']:
                return charset

        # Otherwise, look for a requested charset that Python supports.
        for charset in charsets:
            try:
                'xyz'.encode(charset, 'replace')
                return charset
            except:
                continue

        # If Python doesn't know any of the requested charsets, use UTF-8.
        return 'utf-8'

    def select_locale(self):
        """Detect and activate the appropriate locale.  The 'lang' query
        parameter has priority, then the django_language cookie, then the
        first language in the language menu, then the default setting."""
        default_lang = (self.config and
                        self.config.language_menu_options and
                        self.config.language_menu_options[0])
        lang = (self.params.lang or
                self.request.cookies.get('django_language', None) or
                default_lang or
                django.conf.settings.LANGUAGE_CODE)
        lang = re.sub('[^A-Za-z-]', '', lang)
        self.response.headers.add_header(
            'Set-Cookie', 'django_language=%s' % lang)
        django.utils.translation.activate(lang)
        rtl = django.utils.translation.get_language_bidi()
        self.response.headers.add_header('Content-Language', lang)
        return lang, rtl

    def get_url(self, path, **params):
        """Constructs the absolute URL for a given path and query parameters,
        preserving the current 'subdomain', 'small', and 'style' parameters.
        Parameters are encoded using the same character encoding (i.e.
        self.charset) used to deliver the document."""
        for name in ['subdomain', 'small', 'style']:
            if self.request.get(name) and name not in params:
                params[name] = self.request.get(name)
        if params:
            path += ('?' in path and '&' or '?') + urlencode(params,
                                                             self.charset)
        scheme, netloc, _, _, _ = urlparse.urlsplit(self.request.url)
        return scheme + '://' + netloc + path

    def get_subdomain(self):
        """Determines the subdomain of the request."""

        # The 'subdomain' query parameter always overrides the hostname
        if strip(self.request.get('subdomain', '')):
            return strip(self.request.get('subdomain'))

        levels = self.request.headers.get('Host', '').split('.')
        if levels[-2:] == ['appspot', 'com'] and len(levels) >= 4:
            # foo.person-finder.appspot.com -> subdomain 'foo'
            # bar.kpy.latest.person-finder.appspot.com -> subdomain 'bar'
            return levels[0]

        # Use the 'default_subdomain' setting, if present.
        return config.get('default_subdomain')

    def get_parent_domain(self):
        """Determines the app's domain, not including the subdomain."""
        levels = self.request.headers.get('Host', '').split('.')
        if levels[-2:] == ['appspot', 'com']:
            return '.'.join(levels[-3:])
        return '.'.join(levels)

    def get_start_url(self, subdomain=None):
        """Constructs the URL to the start page for this subdomain."""
        subdomain = subdomain or self.subdomain
        levels = self.request.headers.get('Host', '').split('.')
        if levels[-2:] == ['appspot', 'com']:
            return 'http://' + '.'.join([subdomain] + levels[-3:])
        return self.get_url('/', subdomain=subdomain)

    def send_mail(self, **params):
        """Sends e-mail using a sender address that's allowed for this app."""
        # TODO(kpy): When the outgoing mail queue is added, use it instead
        # of sending mail immediately.
        app_id = os.environ['APPLICATION_ID']
        mail.send_mail(
            sender='Do not reply <do-not-reply@%s.appspotmail.com>' % app_id,
            **params)

    def get_captcha_html(self, error_code=None, use_ssl=False):
        """Generates the necessary HTML to display a CAPTCHA validation box."""

        # We use the 'custom_translations' parameter for UI messages, whereas
        # the 'lang' parameter controls the language of the challenge itself.
        # reCAPTCHA falls back to 'en' if this parameter isn't recognized.
        lang = self.env.lang.split('-')[0]

        return captcha.get_display_html(
            public_key=config.get('captcha_public_key'),
            use_ssl=use_ssl, error=error_code, lang=lang,
            custom_translations={
                # reCAPTCHA doesn't support all languages, so we treat its
                # messages as part of this app's usual translation workflow
                'instructions_visual': _('Type the two words:'),
                'instructions_audio': _('Type what you hear:'),
                'play_again': _('Play the sound again'),
                'cant_hear_this': _('Download the sound as MP3'),
                'visual_challenge': _('Get a visual challenge'),
                'audio_challenge': _('Get an audio challenge'),
                'refresh_btn': _('Get a new challenge'),
                'help_btn': _('Help'),
                'incorrect_try_again': _('Incorrect.  Try again.')
            }
        )

    def get_captcha_response(self):
        """Returns an object containing the CAPTCHA response information for the
        given request's CAPTCHA field information."""
        challenge = self.request.get('recaptcha_challenge_field')
        response = self.request.get('recaptcha_response_field')
        remote_ip = os.environ['REMOTE_ADDR']
        return captcha.submit(
            challenge, response, config.get('captcha_private_key'), remote_ip)

    def handle_exception(self, exception, debug_mode):
        logging.error(traceback.format_exc())
        self.error(500, _(
            'There was an error processing your request.  Sorry for the '
            'inconvenience.  Our administrators will investigate the source '
            'of the problem, but please check that the format of your '
            'request is correct.'))

    def set_content_type(self, type):
        self.response.headers['Content-Type'] = \
            '%s; charset=%s' % (type, self.charset)

    def initialize(self, *args):
        webapp.RequestHandler.initialize(self, *args)
        self.params = Struct()
        self.env = Struct()

        # Log AppEngine-specific request headers.
        for name in self.request.headers.keys():
            if name.lower().startswith('x-appengine'):
                logging.debug('%s: %s' % (name, self.request.headers[name]))

        # Determine the subdomain.
        self.subdomain = self.get_subdomain()

        # Get the subdomain-specific configuration.
        self.config = self.subdomain and config.Configuration(self.subdomain)

        # Log the User-Agent header.
        sample_rate = float(
            self.config and self.config.user_agent_sample_rate or 0)
        if random.random() < sample_rate:
            model.UserAgentLog(
                subdomain=self.subdomain, sample_rate=sample_rate,
                user_agent=self.request.headers.get('User-Agent'),
                ip_address=self.request.remote_addr).put()

        # Choose a charset for encoding the response.
        # We assume that any client that doesn't support UTF-8 will specify a
        # preferred encoding in the Accept-Charset header, and will use this
        # encoding for content, query parameters, and form data.  We make this
        # assumption across all subdomains.
        # (Some Japanese mobile phones support only Shift-JIS and expect
        # content, parameters, and form data all to be encoded in Shift-JIS.)
        self.charset = self.select_charset()
        self.request.charset = self.charset
        self.set_content_type('text/html')  # add charset to Content-Type header

        # Validate query parameters.
        for name, validator in self.auto_params.items():
            try:
                value = self.request.get(name, '')
                setattr(self.params, name, validator(value))
            except Exception, e:
                setattr(self.params, name, validator(None))
                return self.error(400, 'Invalid parameter %s: %s' % (name, e))

        if self.params.flush_cache:
            # Useful for debugging and testing.
            memcache.flush_all()
            global_cache.clear()
            global_cache_insert_time.clear()

        # Activate localization.
        lang, rtl = self.select_locale()

        # Put common non-subdomain-specific template variables in self.env.
        self.env.charset = self.charset
        self.env.url = set_url_param(self.request.url, 'lang', lang)
        self.env.netloc = urlparse.urlparse(self.request.url)[1]
        self.env.domain = self.env.netloc.split(':')[0]
        self.env.parent_domain = self.get_parent_domain()
        self.env.lang = lang
        self.env.virtual_keyboard_layout = VIRTUAL_KEYBOARD_LAYOUTS.get(lang)
        self.env.rtl = rtl
        self.env.back_chevron = rtl and u'\xbb' or u'\xab'
        self.env.analytics_id = get_secret('analytics_id')
        self.env.maps_api_key = get_secret('maps_api_key')

        # Provide the status field values for templates.
        self.env.statuses = [Struct(value=value, text=NOTE_STATUS_TEXT[value])
                             for value in pfif.NOTE_STATUS_VALUES]

        # Check for SSL (unless running on localhost for development).
        if self.https_required and self.env.domain != 'localhost':
            scheme = urlparse.urlparse(self.request.url)[0]
            if scheme != 'https':
                return self.error(403, 'HTTPS is required.')

        # Check for an authorization key.
        self.auth = None
        if self.subdomain and self.params.key:
            self.auth = model.Authorization.get(self.subdomain, self.params.key)

        # Handlers that don't need a subdomain configuration can skip it.
        if not self.subdomain:
            if self.subdomain_required:
                return self.error(400, 'No subdomain specified.')
            return

        # Reject requests for subdomains that haven't been activated.
        if not model.Subdomain.get_by_key_name(self.subdomain):
            return self.error(404, 'No such domain.')

        # To preserve the subdomain properly as the user navigates the site:
        # (a) For links, always use self.get_url to get the URL for the HREF.
        # (b) For forms, use a plain path like "/view" for the ACTION and
        #     include {{env.subdomain_field_html}} inside the form element.
        subdomain_field_html = (
            '<input type="hidden" name="subdomain" value="%s">' %
            self.request.get('subdomain', ''))

        # Put common subdomain-specific template variables in self.env.
        self.env.subdomain = self.subdomain
        self.env.subdomain_title = get_local_message(
                self.config.subdomain_titles, lang, '?')
        self.env.keywords = self.config.keywords
        self.env.family_name_first = self.config.family_name_first
        self.env.use_family_name = self.config.use_family_name
        self.env.use_alternate_names = self.config.use_alternate_names
        self.env.use_postal_code = self.config.use_postal_code
        self.env.map_default_zoom = self.config.map_default_zoom
        self.env.map_default_center = self.config.map_default_center
        self.env.map_size_pixels = self.config.map_size_pixels
        self.env.language_api_key = self.config.language_api_key
        self.env.subdomain_field_html = subdomain_field_html
        self.env.main_url = self.get_url('/')
        self.env.embed_url = self.get_url('/embed')
        # TODO(ryok): The following if statements are necessary only during the
        # transition of {main|results}_page_custom_html(s) options from the old
        # plain text format to the new i18n'ed dictionary format.  Remove these
        # once the transition is complete.
        if self.config.main_page_custom_html:
            self.env.main_page_custom_html = self.config.main_page_custom_html
        else:
            self.env.main_page_custom_html = get_local_message(
                    self.config.main_page_custom_htmls, lang, '')
        if self.config.results_page_custom_html:
            self.env.results_page_custom_html = \
                self.config.results_page_custom_html
        else:
            self.env.results_page_custom_html = get_local_message(
                    self.config.results_page_custom_htmls, lang, '')
        self.env.jp_mobile_carrier_redirect = \
            self.config.jp_mobile_carrier_redirect

        # Provide the contents of the language menu.
        self.env.language_menu = [
            {'lang': lang,
             'endonym': LANGUAGE_ENDONYMS.get(lang, '?'),
             'url': set_url_param(self.request.url, 'lang', lang)}
            for lang in self.config.language_menu_options or []
        ]

        # If this subdomain has been deactivated, terminate with a message.
        if self.config.deactivated and not self.ignore_deactivation:
            self.env.language_menu = []
            self.render('templates/message.html', cls='deactivation',
                        message_html=self.config.deactivation_message_html)
            self.terminate_response()

    def is_test_mode(self):
        """Returns True if the request is in test mode. Request is considered
        to be in test mode if the remote IP address is the localhost and if
        the 'test_mode' HTTP parameter exists and is set to 'yes'."""
        post_is_test_mode = validate_yes(self.request.get('test_mode', ''))
        client_is_localhost = os.environ['REMOTE_ADDR'] == '127.0.0.1'
        return post_is_test_mode and client_is_localhost

    def head(self, **kwargs):
        """Default implementation for a HEAD request."""
        self.get(**kwargs)
        self.response.body = ''


def run(*mappings, **kwargs):
    webapp.util.run_wsgi_app(webapp.WSGIApplication(list(mappings), **kwargs))
