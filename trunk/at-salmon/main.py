#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import datetime
import re
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext.webapp import logging

import imports
import magicsig

class Comment(db.Expando):
  author = db.UserProperty(required=True)
  posted_at = db.DateTimeProperty(required=True)
  content = db.TextProperty(required=True)
  mentions = db.StringListProperty()
  
class MainHandler(webapp.RequestHandler):

  def get(self):
    user = users.get_current_user()
    if user:
      commentResults = db.GqlQuery("SELECT * FROM Comment")
      mentionResults = self.fetch_mentions_for_user(user)
      comments = []
      mentions = []
      for comment in commentResults:
        comments.append(self.decorate_comment(comment))
      for mention in mentionResults:
        mentions.append(self.decorate_comment(comment))

      template_values = {
        'comments': comments,
        'mentions': mentions,
        'user': user.email(),
        'logout_url': users.create_logout_url('/') }
      path = os.path.join(os.path.dirname(__file__), 'index.html')
      self.response.out.write(template.render(path, template_values))
    else:
      greeting = ("<a href=\"%s\">Sign in or register</a>." %
                  users.create_login_url("/"))
      self.response.out.write(greeting)

  def fetch_mentions_for_user(self, user): 
    mentions = db.GqlQuery("SELECT * FROM Comment where mentions = :user_uri", user_uri=user.email())
    return mentions

  def decorate_comment(self, comment):
    comment.decorated_content = comment.content

    for mention in comment.mentions:
      replacer = re.compile(mention)
      linkedMention = "<a href='' title='Link to something on about %s'>%s</a>" % (mention, mention)
      comment.decorated_content = replacer.sub(linkedMention, comment.decorated_content)

    return comment


def extract_mentions(text):
  # http://stackoverflow.com/questions/201323/what-is-the-best-regular-expression-for-validating-email-addresses :)
  #mentionsRegex = re.compile('@[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+.[a-zA-Z0-9-.]+')
  mentionsRegex = re.compile('@[^\s]+') #@-anything followed by a space
  matches = mentionsRegex.findall(text)
  mentions = []
  for match in matches:
    match = match[1:len(match)] # remove leading @
    mentions.append(match)
  return list(set(mentions)) #set() to de-dupe


class CommentHandler(webapp.RequestHandler):
  def post(self):
    comment_text = self.request.get('comment-text')
    comment_mentions = extract_mentions(comment_text)
    comment_text = self.request.get('comment-text')

    c = Comment(
      author = users.get_current_user(), 
      posted_at = datetime.datetime.now(),
      content = comment_text,
      mentions = comment_mentions)
    c.put()

    self.response.out.write("thanks");
    self.redirect('/');


class SalmonSlapHandler(webapp.RequestHandler):
  def post(self):
    # Retrieve putative Salmon from input body.
    body = self.request.body
    mime_type = self.request.headers['Content-Type']
    envelope = magicsig.Envelope(
        document=body,
        mime_type=mime_type)
    # If we got here, the Salmon validated.

    # The following is crap, we need to get a much better
    # data access mechanism in place: 
    xml = envelope.GetParsedData()
    author = xml.getElementsByTagName('author')[0].getElementsByTagName('uri')[0].firstChild.data.strip()
    posted_at_str = xml.getElementsByTagName('updated')[0].firstChild.data.strip()
    content = xml.getElementsByTagName('content')[0].firstChild.data.strip()
    # End of crap.

    author = users.User(re.sub('^acct:','',author))

    mentions = extract_mentions(content)

    logging.info('About to add: author=%s, content=%s, mentions=%s' % (author,
                                                                       content,
                                                                       mentions))

    c = Comment(
        author=author,
        posted_at=datetime.datetime.now(),  #should convert posted_at_str,
        content=content,
        mentions=mentions)
    c.put()
    self.response.set_status(202)
    self.response.out.write("Salmon accepted!\n")


def main():
  application = webapp.WSGIApplication(
      [
          ('/', MainHandler),
          ('/comment', CommentHandler),
          ('/salmon-slap', SalmonSlapHandler),
      ],
      debug=True)
  util.run_wsgi_app(application)


if __name__ == '__main__':
  main()