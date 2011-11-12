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

from datetime import datetime
from model import *
from photo import get_photo_url
from utils import *
from detect_spam import SpamDetector
from google.appengine.api import images
from google.appengine.runtime.apiproxy_errors import RequestTooLargeError
import indexing
import prefix

from django.utils.translation import ugettext as _

MAX_IMAGE_DIMENSION = 300

def validate_date(string):
    """Parses a date in YYYY-MM-DD format.    This is a special case for manual
    entry of the source_date in the creation form.    Unlike the validators in
    utils.py, this will throw an exception if the input is badly formatted."""
    year, month, day = map(int, string.strip().split('-'))
    return datetime(year, month, day)

def days_to_date(days):
    """Converts a duration signifying days-from-now to a datetime object.

    Returns:
      None if days is None, else now + days (in utc)"""
    return days and get_utcnow() + timedelta(days=days)

def validate_names(params, config):
    """Validates the name parameters according to the config.

    Returns:
      None if the params are valid, else error400message"""

    if config.use_family_name:
        if not (params.first_name and params.last_name):
            return _('The Given name and Family name are both required.  Please go back and try again.')
    else:
        if not params.first_name:
            return _('Name is required.  Please go back and try again.')
    if not params.author_name:
        if params.clone:
            return _('The Original author\'s name is required.  Please go back and try again.')
        else:
            return _('Your name is required in the "Source" section.  Please go back and try again.')
    return None

def validate_note(params, config):
    """Validates the note parameters per the config.

    Returns:
      None if the params are valid, else error400message"""
    if params.add_note:
        if not params.text:
            return _('Message is required. Please go back and try again.')
        if params.status == 'is_note_author' and not params.found:
            return _('Please check that you have been in contact with the person after the earthquake, or change the "Status of this person" field.')
        if (params.status == 'believed_dead' and not config.allow_believed_dead_via_ui):
            return _('Not authorized to post notes with the status "believed_dead".')
    return None

def validate_dates(params, config, now):
    """Validates the date parameters according to the config
    and the current time.

    Returns:
      None if the params are valid, else error400message"""
    source_date = None
    if params.source_date:
        try:
            source_date = validate_date(params.source_date)
        except ValueError:
            return _('Original posting date is not in YYYY-MM-DD format, or is a nonexistent date.  Please go back and try again.')
        if source_date > now:
            return _('Date cannot be in the future.  Please go back and try again.')
    return None

def validate_params(params, config, now):
    """Validates the given params according to the config.

    Returns:
      None if the params are valid, else error400message"""
    return validate_names(params, config) \
        or validate_note(params, config) \
        or validate_dates(params, config, now)

class Create(Handler):
    def get(self):
        self.params.create_mode = True
        self.render('templates/create.html',
                    onload_function='view_page_loaded()')

    def post(self):
        now = get_utcnow()

        error_message = validate_params(self.params, self.config, now)
	if error_message: 
		return self.error(400, error_message)

        source_date = None
        if self.params.source_date:
            source_date = validate_date(self.params.source_date)

        expiry_date = days_to_date(self.params.expiry_option or 
                                   self.config.default_expiry_days)

        # If nothing was uploaded, just use the photo_url that was provided.
        photo = None
        photo_url = self.params.photo_url

        # If a picture was uploaded, store it and the URL where we serve it.
        photo_obj = self.params.photo
        # if image is False, it means it's not a valid image
        if photo_obj == False:
            return self.error(400, _('Photo uploaded is in an unrecognized format.  Please go back and try again.'))

        if photo_obj:
            if max(photo_obj.width, photo_obj.height) <= MAX_IMAGE_DIMENSION:
                # No resize needed.  Keep the same size but add a
                # transformation so we can change the encoding.
                photo_obj.resize(photo_obj.width, photo_obj.width)
            elif photo_obj.width > photo_obj.height:
                photo_obj.resize(
                    MAX_IMAGE_DIMENSION,
                    photo_obj.height * (MAX_IMAGE_DIMENSION / photo_obj.width))
            else:
                photo_obj.resize(
                    photo_obj.width * (MAX_IMAGE_DIMENSION / photo_obj.height),
                    MAX_IMAGE_DIMENSION)

            try:
                sanitized_photo = \
                    photo_obj.execute_transforms(output_encoding=images.PNG)
            except RequestTooLargeError:
                return self.error(400, _('The provided image is too large.  Please upload a smaller one.'))
            except Exception:
                # There are various images.Error exceptions that can be raised,
                # as well as e.g. IOError if the image is corrupt.
                return self.error(400, _('There was a problem processing the image.  Please try a different image.'))

            photo = Photo(bin_data=sanitized_photo)
            photo.put()
            photo_url = get_photo_url(photo)

        other = ''
        if self.params.description:
            indented = '    ' + self.params.description.replace('\n', '\n    ')
            indented = indented.rstrip() + '\n'
            other = 'description:\n' + indented

        # Person records have to have a source_date; if none entered, use now.
        source_date = source_date or now

        # Determine the source name, or fill it in if the record is original
        # (i.e. created for the first time here, not copied from elsewhere).
        source_name = self.params.source_name
        if not self.params.clone:
            source_name = self.env.netloc  # record originated here

        person = Person.create_original(
            self.subdomain,
            entry_date=now,
            expiry_date=expiry_date,
            first_name=self.params.first_name,
            last_name=self.params.last_name,
            alternate_first_names=self.params.alternate_first_names,
            alternate_last_names=self.params.alternate_last_names,
            sex=self.params.sex,
            date_of_birth=self.params.date_of_birth,
            age=self.params.age,
            home_street=self.params.home_street,
            home_city=self.params.home_city,
            home_state=self.params.home_state,
            home_postal_code=self.params.home_postal_code,
            home_neighborhood=self.params.home_neighborhood,
            home_country=self.params.home_country,
            author_name=self.params.author_name,
            author_phone=self.params.author_phone,
            author_email=self.params.author_email,
            source_url=self.params.source_url,
            source_date=source_date,
            source_name=source_name,
            photo=photo,
            photo_url=photo_url,
            other=other
        )
        person.update_index(['old', 'new'])

        if self.params.add_note:
            if person.notes_disabled:
                return self.error(403, _(
                    'The author has disabled status updates on this record.'))

            spam_detector = SpamDetector(self.config.badwords)
            spam_score = spam_detector.estimate_spam_score(self.params.text)
            if (spam_score > 0):
                note = NoteWithBadWords.create_original(
                    self.subdomain,
                    entry_date=get_utcnow(),
                    person_record_id=person.record_id,
                    author_name=self.params.author_name,
                    author_email=self.params.author_email,
                    author_phone=self.params.author_phone,
                    source_date=source_date,
                    found=bool(self.params.found),
                    status=self.params.status,
                    email_of_found_person=self.params.email_of_found_person,
                    phone_of_found_person=self.params.phone_of_found_person,
                    last_known_location=self.params.last_known_location,
                    text=self.params.text,
                    spam_score=spam_score,
                    confirmed=False)

                # Write the new NoteWithBadWords to the datastore
                db.put(note)
                # Write the person record to datastore before redirect
                db.put(person)

                # When the note is detected as spam, we do not update person 
                # record with this note or log action. We ask the note author 
                # for confirmation first.
                return self.redirect('/post_flagged_note', id=note.get_record_id(),
                                     author_email=note.author_email,
                                     subdomain=self.subdomain)
            else:
                note = Note.create_original(
                    self.subdomain,
                    entry_date=get_utcnow(),
                    person_record_id=person.record_id,
                    author_name=self.params.author_name,
                    author_email=self.params.author_email,
                    author_phone=self.params.author_phone,
                    source_date=source_date,
                    found=bool(self.params.found),
                    status=self.params.status,
                    email_of_found_person=self.params.email_of_found_person,
                    phone_of_found_person=self.params.phone_of_found_person,
                    last_known_location=self.params.last_known_location,
                    text=self.params.text)

                # Write the new NoteWithBadWords to the datastore
                db.put(note)
                person.update_from_note(note)

            # Specially log 'believed_dead'.
            if note.status == 'believed_dead':
                detail = person.first_name + ' ' + person.last_name
                UserActionLog.put_new(
                    'mark_dead', note, detail, self.request.remote_addr)

        # Write the person record to datastore
        db.put(person)

        if not person.source_url and not self.params.clone:
            # Put again with the URL, now that we have a person_record_id.
            person.source_url = self.get_url('/view', id=person.record_id)
            db.put(person)

        # If user wants to subscribe to updates, redirect to the subscribe page
        if self.params.subscribe:
            return self.redirect('/subscribe', id=person.record_id,
                                 subscribe_email=self.params.author_email)

        self.redirect('/view', id=person.record_id)

if __name__ == '__main__':
    run(('/create', Create))
