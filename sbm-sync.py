#!-*- coding:utf-8 -*-
import os
import cgi
import logging
import yaml
import base64
import datetime
import urllib
import xmllib
import elementtree.SimpleXMLTreeBuilder as xmlbuilder

import wsgiref.handlers
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template

class Bookmark(db.Model):
  url = db.StringProperty(required=True)
  description = db.StringProperty(required=True)
  extended = db.StringProperty()
  tags = db.StringProperty()
  timestamp = db.DateTimeProperty(required=True, auto_now=True)

class BookmarkSync(webapp.RequestHandler):
  def get(self):
    config = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), 'my-config.yaml'), 'r'))
    try:
      content = urlfetch.fetch('http://b.hatena.ne.jp/%s/rss' % config['hatena_user']).content
      parser = xmlbuilder.TreeBuilder()
      xmllib.XMLParser.__init__(parser, accept_utf8=1)
      parser.feed(content)
      dom = parser.close()
      entries = dom.findall('{http://purl.org/rss/1.0/}item')
      count = 0
      for entry in entries:
        url = entry.find('{http://purl.org/rss/1.0/}link').text
        logging.info('checking:' + url)
        if Bookmark.gql('WHERE url=:url', url=url).get(): continue
        logging.info('posting:' + url)
        description = entry.find('{http://purl.org/rss/1.0/}title').text or ''
        extended = entry.find('{http://purl.org/rss/1.0/}description').text or ''
        tags = ' '.join([x.text for x in entry.findall('{http://purl.org/dc/elements/1.1/}subject')]) or ''
        uri = 'https://api.del.icio.us/v1/posts/add?' + urllib.urlencode({ 'url' : url, 'description' : description, 'extended' : extended, 'tags' : tags })
        try:
          auth = base64.b64encode('%s:%s' % (config['delicious_user'], config['delicious_pass'])).strip("\n")
          res = urlfetch.fetch(uri, headers={ 'Authorization' : 'Basic %s' % auth }).status_code
          Bookmark(url = url.decode('utf-8'), description = description.replace("\n", '').decode('utf-8'), extended = extended.decode('utf-8'), tags = tags.decode('utf-8')).put()
          logging.info('posted:' + url)
        except Exception, e:
          logging.error(e)
          logging.info('failed:' + url)
          pass
        count = count + 1
        if count > 5: break
      self.response.out.write('done')
    except:
      self.response.out.write('failed')

class MainPage(webapp.RequestHandler):
  def get(self):
    config = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), 'plagger-config.yaml'), 'r'))
    recent = Bookmark.all().order('-timestamp').fetch(10)
    template_values = {
      'recent' : recent,
      'delicious_user' : config['delicious_user'],
      'hatena_user' : config['hatena_user'],
      'hatena_icon' : 'http://www.hatena.ne.jp/users/%s/%s/profile_s.gif' % (config['hatena_user'][0:2], config['hatena_user']),
      'timezone' : config['timezone'],
      'updated' : recent[0].timestamp + datetime.timedelta(hours=int(config['timeoffset'])),
    }
    path = os.path.join(os.path.dirname(__file__), 'sbm-sync.html')
    self.response.out.write(template.render(path, template_values))

def main():
  application = webapp.WSGIApplication([
    ('/tasks/sbm-sync', BookmarkSync),
    ('/', MainPage),
  ], debug=False)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()
