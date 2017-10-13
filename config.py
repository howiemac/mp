"""
config file for app

"""

default_class="Page"
urlpath=""  # no /evoke in url

attribution=False
show_time=False
avatars=False
thumb_size=200

meta_description="music player, VLC, music database" #site description text for search engines
meta_keywords="music, VLC" #comma separated list of keywords for search engines

from evoke.data.schema import *

class Page(Schema):
  table='pages'
  code=TAG,KEY
  parent=INT,KEY # defines a hierarchy
#  rel=INT,KEY    # allows an alternate hierarchy
  lineage=STR
  name=TAG,KEY
  kind=TAG,KEY
  stage=TAG,'live',KEY
  when=DATE,now
  text=TEXT,KEY
  seq=INT,KEY
  rating=INT
  prefs=TEXT
  score=INT

# EXTRA FIELDS START HERE
  artist=TAG,KEY
  composer=TAG
  length=INT  # length in milliseconds
  version=TEXT,KEY

  insert=[
    dict(uid=1,parent=1,name='mp vlc',kind='root',lineage="."),
    dict(uid=2,parent=1,code='admin',name='admin',kind='admin',lineage=".1."),
    dict(uid=3,parent=1,name='artists',kind='artists',lineage=".1."),
    dict(uid=4,parent=3,name='Various Artists',kind='artist',stage='posted',lineage=".1.3."),
    dict(uid=5,parent=1,name='Playlists',kind='playlists',stage='live',lineage=".1."),
    dict(uid=6,parent=1,name='Genres',kind='genres',stage='live',lineage=".1."),
    dict(uid=7,parent=2,name='additions',kind='smartlist',stage='posted',lineage=".1.2.",text="order by uid desc"),
    ]


class Tag(Schema):
  table='tags'
  name=TAG,KEY
  page=INT,KEY
  
class Play(Schema):
  table='plays'
  when=DATE,now,KEY  
  page=INT,KEY
  times=INT  
  

