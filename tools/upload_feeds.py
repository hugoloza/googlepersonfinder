import csv

import importer
import remote_api
import api

FILE = '/tmp/persons.csv'
HOST = 'googlepersonfinder.appspot.com'
REPO = '2013-yolanda'
EMAIL = ''
PASSWORD = ''
DOMAIN = '2013-yolanda.personfinder.google.org'
BELIEVED_DEAD_PERMISSION = False
ALLOW_OVERWRITE = False
DRY_RUN = True

remote_api.connect(HOST, EMAIL, PASSWORD)

lines = open(FILE).read().splitlines()  # handles \r, \n, or \r\n
records = importer.utf8_decoder(api.convert_time_fields(csv.reader(lines)))
records = [api.complete_record_ids(r, DOMAIN) for r in records]

is_not_empty = lambda x: (x or '').strip()
persons = [r for r in records if is_not_empty(r.get('full_name'))]
notes = [r for r in records if is_not_empty(r.get('note_record_id'))]

people_written, people_skipped, people_total = importer.import_records(
    REPO, DOMAIN, importer.create_person, persons,
    omit_duplicate_persons=True,
    allow_overwrite=ALLOW_OVERWRITE,
    dry_run=DRY_RUN)
notes_written, notes_skipped, notes_total = importer.import_records(
    REPO, DOMAIN, importer.create_note, notes,
    believed_dead_permission=BELIEVED_DEAD_PERMISSION,
    omit_duplicate_notes=True,
    allow_overwrite=ALLOW_OVERWRITE,
    dry_run=DRY_RUN)

print 'PERSON written %d / %d' % (len(people_written), people_total)
print 'NOTE written %d / %d' % (len(notes_written), notes_total)
print 'PERSON errors ==============================='
print people_skipped
print 'NOTE errors ==============================='
print notes_skipped
