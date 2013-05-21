import calendar, datetime, model, pickle, sys
from google.appengine.api import users
from google.appengine.ext import db

def msg(text, *args):
  if args:
    text = text % args
  sys.stderr.write(text)
  sys.stderr.flush()

def to_value(v):
  """Converts google.appengine.api.datastore_types to plain Python values."""
  # google.appengine.api uses subclasses of unicode like Text, Email, etc.
  if isinstance(v, unicode):
    return unicode(v)
  if isinstance(v, str):
    return str(v)
  if isinstance(v, long):
    return long(v)
  if isinstance(v, datetime.datetime):
    return calendar.timegm(v.utctimetuple())
  if db:
    if isinstance(v, db.Key):
      return v.to_path()
    if isinstance(v, db.BlobKey):
      return str(v)
  if users:
    if isinstance(v, users.User):
      return dict((k, getattr(v, k)())
                  for k in 'user_id email nickname auth_domain'.split())
  return v

def to_dict(e):
  """Converts a db.Model instance to a plain dictionary."""
  return dict([(k, to_value(getattr(e.__class__, k).get_value_for_datastore(e)))
               for k in e.properties().keys()] +
              [(k, to_value(getattr(e, k))) for k in e.dynamic_properties()],
              key=e.key().to_path(), key_name=e.key().name())

def fetch_all(query):
  batch = query.fetch(100)
  count = 0
  while batch:
    msg('.')
    for entity in batch:
      count += 1
      yield entity
    query = query.with_cursor(query.cursor())
    batch = query.fetch(100)
  msg('%d\n', count)

def get_counters(repo):
  return fetch_all(
      model.Counter.all().filter('repo =', repo).filter('last_key =', ''))

def get_persons(repo):
  return fetch_all(model.Person.all_in_repo(repo, filter_expired=False))

def get_notes(repo):
  return fetch_all(model.Note.all_in_repo(repo, filter_expired=False))

def get_subscriptions(repo):
  return fetch_all(model.Subscription.all().filter('repo =', repo))

def get_user_action_logs(repo):
  return fetch_all(model.UserActionLog.all().filter('repo =', repo))

def save(filename, entities):
  msg('Writing %s: ', filename)
  f = open(filename, 'w')
  pickle.dump([to_dict(e) for e in entities], f)
  f.close()

def load(filename):
  f = open(filename)
  data = pickle.load(f)
  f.close()
  return data

def save_all(repo):
  save(repo + '.person.pickle', get_persons(repo))
  save(repo + '.note.pickle', get_notes(repo))
  save(repo + '.subscription.pickle', get_subscriptions(repo))
  save(repo + '.log.pickle', get_user_action_logs(repo))
