"""
music library override class for evoke.page 
"""

import random
import os
import sys
import urllib.request, urllib.parse, urllib.error
import types
import imghdr
import shutil
from copy import copy
from datetime import datetime

#from . 
import vlc 
from twisted.internet import reactor

from evoke.data import execute
from evoke.render import html
from evoke.serve import Req
from evoke.lib import *
from evoke.Page import Page as basePage

## for temp/testing only
#from musicmeta import meta
#from itunes_xrefs import xref


class Page(basePage):

  imageaddkinds=basePage.imageaddkinds+['artists','artist','album','track']
  fileaddkinds=imageaddkinds
  musickinds=['artists','artist','album','track','playlists','genres','playlist','smartlist']
  playablekinds=['root','artist','album','track','playlist','smartlist']
  postkinds=basePage.postkinds+['artist','album','track','playlist','smartlist']
  ratedkinds=['artist','album','track','playlist','smartlist'] # kinds that a rating can be set for
  playlistkinds=['root','playlist','smartlist']
 
  validchildkinds={
   'artists':['artist'],
   'artist':['album'],
   'album':['track'],
   'track':[],
   'playlists':['smartlist','playlist'],
   'genres':['smartlist'],
   }
 
  # extra data #################
  
  def save_text(self,req):
    "deal with extra items - notably the tabs and track dates"
    self.update_tags(req)
    # ensure that track/album has an artist  
    if not req.artist:
      if self.kind=='track': 
        req.artist=self.get_pob().get_pob().name  # use the album artist
      elif self.kind=='album':
        req.artist=self.get_pob().name
    o=basePage.save_text(self,req)# this does, inter alia, an update(req) and flush()
    # now that we have updated self.when, update the children, if requested
    if req.trackdates and (self.kind=='album'): # make the track dates (when) the same as the album date
      for i in self.get_children_by_kind(kind='track'):
        i.when=self.when
        i.flush()
    return o


  # handling of extra kinds #############

  def set_seq(self):
    "override for set_seq"
    if self.kind=='track':
      pass # tracks use seq for track number, so don't allow change here
    else: 
      basePage.set_seq(self)  

  def get_order(self):
    "override for the basePage version - to include artist and score orders"
    pref=self.get_pref('order_by')
    if pref=='artist':
      order='artist,name'
    elif pref=='score':
      order='score desc'
    elif pref=='latest':
      order='uid desc'
    else:
      order=basePage.get_order(self,pref)  
    return order

  def add_page(self,req):
    "override the default to add new genres"
    # add required data to req 
    if req.kind=='album':
      req.artist=self.name
    elif req.kind=='track':
      req.artist=self.artist
    # do the default create  
    page=self.create_page(req)
    # fix for adding genres, and return
    if page and req.name and self.name=='genres':
      page.add_tag(req.name) # add the new genre, by adding a tag for it
      req.message="genre %s added" % req.name 
      return self.view(req)
    return page.redirect(req,'edit') # default is to return new page in edit mode


  def can_move_here(self,req):
    "is it okay to move or copy the  move object here - can be overridden by inheriting classes"
    move=basePage.can_move_here(self,req)
    if move and self.kind in self.validchildkinds and not move.kind in self.validchildkinds[self.kind]:
      move=None
    return move

  def get_smart_playlist(self,req=None,objects=False,info=False):
    '''return a list of track uids (or objects, if requested) per smartlist criteria
      
    if info is True, will return only the search criteria
    
    can set artist and/or tabs and/or (in self.text) where/orderby/limit sql
    
    self.text can (legitimately) contain:
      - where clause
      - order by
      - limit
    '''
    db=self.Config.database
    # get tags, if any
    tags=self.get_tags()
    select="select pages.%s from `%s`.pages " % (objects and '*' or 'uid',db)
    if tags:
      select+="inner join `%s`.tags on tags.page=pages.uid " % (db,)
      if len(tags)==1:
        tagclause="tags.name='%s'" % tags[0]
      else:
        tagclause="tags.name in %s" % str(tuple(tags))  
    else:
      tagclause=""
    # add artist, if any
    artistclause= self.artist and ("artist='%s'" % self.artist) or ""
    # add rating clause - show everything at chosen rating or better
    rat=self.minrating()
    ratingclause= ("rating>=%s " % rat) if rat>-4 else ""
    # add text, if any - allow a starting "where " but ignore it
    t=self.text.strip()
    if (t.startswith('order by') or t.startswith('limit')):
      textclause=""
      finalclause=t
    else:
      textclause=t.startswith('where ') and t[6:] or t
      finalclause="" 
    # are we just returning info?
    if info: # we are done - return the criteria
      ratinginfo=("rating%s%s " % ('=' if self.rating==2 else '>=',self.get(1).rating_symbol())) if self.rating>-4 else ""
      wheres=' and '.join(i for i in (tagclause,artistclause,ratinginfo,textclause) if i)
      return "tracks %s%s %s" % ('where ' if wheres else "",wheres,finalclause)
    # put it all together and execute the query
    where="where %s " % (' and '.join(i for i in ("kind='track'",tagclause,artistclause,ratingclause,textclause) if i),)
    sql=select+where+finalclause
    try:
      if objects:
        sl=[self.get(i['uid'],data=i) for i in execute(sql)]
      else:
        sl=[i["uid"] for i in execute(sql)]
    except BaseException as e:
      sl=[]
      if req:
        req.smartlist_error='invalid query: %s' % e
      else:
        print("<<<< EXCEPTION >>>>", e)
#      raise
    return sl

  def get_dumb_playlist(self,objects=False):
    '''gets list of track uids (or objects, if requested) from playlist or root kind (as opposed to a smartlist, or album playlist)

       also checks for invalid items, and removes them from the playlist (brute force method - does this every time!)
    '''
    rawuids=[safeint(i) for i in self.text.split('\n')]
    uids=[uid for uid in rawuids if uid]
#    print ">>>> uids=",uids
    playlist=[]
    ok=True
    for i in uids:
        try: # make sure it exists
            x=self.get(i)
        except:
            x=False
        if x and x.kind=='track': # add it to the playlist
            playlist.append(x)
        else: #flag to update the playlist
            ok=False
#    print ">>>> dumb playlist=",playlist
    if not ok: #fix the playlist
        self.text='\n'.join([str(i.uid) for i in playlist])
        self.flush()
#    print ">>>> fixed dumb playlist=",[i.uid for i in playlist]
    # filter for rating - only include items of given rating or better
    if self.kind!='root': # no rating filter for the root playorder
      playlist=[i for i in playlist if i.rating>=self.minrating()]
#      if not objects: # filter the uids only if we need to
#        uids=[i.uid for i in playlist]
#      print ">>>> filtered dumb playlist=",[i.uid for i in playlist]
    return playlist if objects else [i.uid for i in playlist]

#  def get_playorder(self):
#    """ returns simply the uids of a dumb playlist 
#     No checking or filtering.
#     Used for the play order: uid=1, kind=="root"
#    """
#    uids=[safeint(i) for i in self.text.split('\n') if safeint(i)]
#    return uids


  def get_album_playlist(self):
    "returns list of all enabled track objects on that (self) album, in seq order"
    return self.list(parent=self.uid,kind='track',where='rating>=%s' % self.minrating(),orderby='seq,uid')

  def get_artist_playlist(self):
    "returns list of all enabled track objects by that artist (self), in current pref album sort order, and album seq within that"
    playlist=[]
    for album in self.list(parent=self.uid,kind='album',orderby=self.get_order()):
      playlist.extend(album.get_album_playlist())
    return playlist

  def get_playlist_section(self,req):
    """return a list of 50 playlist objects from req._pl_start
     optional param: req._pl_start
    """
#    if self.kind=='root':
#      playlist=self.get_playorder()
    if self.kind in ('root','playlist'):
      playlist= self.get_dumb_playlist(objects=True)
    else:# must be a smart playlist
      playlist=self.get_smart_playlist(req,objects=True)
    if playlist:  # if we have at least one integer value
      # set start and end
      start=safeint(req._pl_start)
      # find current index
      curr=self.transport.uid
      p=0 if curr else -1
      # if we are playing a track and we are in the root or current playlist...
      if curr and ((self.uid==1) or (self.player.list and (self.uid==self.player.list.uid))):
        # adjust _pl_start to display the currently playing track near the top of the list if possible
        # try using the index to find the track in the playlist - this should work
        try:
          p=self.get_index()
          assert playlist[p].uid==curr
        except:
          p=0
#          raise
          # otherwise, look for the currently playing track by uid
#          try:
#            p=playlist.index(self.transport.uid) # find the current track
#          except:
#            raise
#            p=0
#        print "got p:",p
        if ("_pl_start" not in req) and (p>start):
          start=max(0,p-2) # adjust start so that the current track is third or less on the list
      # adjust end, and set more req parameters
      end=start+50
      req._pl_index=p
      req._pl_start=start
      if start:
        req._pl_back=max(0,start-50)
      if len(playlist)>end:
        req._pl_more=end
      req._pl_len=len(playlist)
#      print "start=",start,"  end=",end," index=",req._pl_index,"  more=",req._pl_more,"  back=",req._pl_back, " len=",len(playlist)
      return playlist[start:end]
    return []

  def get_playlist(self):
      "get a playlist for playing (or playnext)"
      # call the appropriate playlist constructor
      if self.kind=='track':
        playlist=[self]
      elif self.kind=='album':
        playlist=self.get_album_playlist()
      elif self.kind=='artist':
        playlist=self.get_artist_playlist()
      elif self.kind=='smartlist':
        playlist=self.get_smart_playlist(objects=True) 
      elif self.kind in ('root','playlist'):
        playlist=self.get_dumb_playlist(objects=True)
      # shuffle, if necessary
#      if len(playlist)>1 and self.player.is_shuffling:
      if len(playlist)>1 and hasattr(self,"shuffling"):
        random.shuffle(playlist) 
      # and return  
      return playlist
  
  
  
  def get_images(self):
    "enhance evoke.Page.py - so that track with no images inherits from album, and album from artist"
    images=basePage.get_images(self)
    if not images and self.kind in ('track','album'):
      pob=self.get_pob()
      image=pob.get_image()
      if image:
#        if self.kind=='track':
#          image.stage="right full 300x300 120x120"# override, to make image smaller
#        elif self.kind=='album':
#          image.stage="right full 500x500 120x120"# override
        image.composer=pob.url() #store linkto album in here
        images=[image]  # don't cache the inherited image in self.images - so self.images can be used to get only the child images
    return images 
    
  # tags #####################
  
  def get_tags(self):
    "return a list of tags for this page"
    return [i.name for i in self.Tag.list(page=self.uid, orderby='uid')]

  def get_tagnames(self):
    "return a list of currently used tagnames"
    return [str(i.get('name')) for i in self.Tag.list(asObjects=False,what="distinct name", orderby="name")]

  def add_tag(self,tag):
    "add a new tag - returning its tag object"
    tob=self.Tag.new()
    tob.name=tag
    tob.page=self.uid
    tob.flush()
    if self.kind=='track': # update album tags to reflect new addition
      album=self.get_pob()
      if not tag in album.get_tags():
        album.add_tag(tag)
    return tob

  def update_tags(self,req):
    "edit update for tags"
#    print ">>>>>>>>>>>>>>", req
    if 'tag1' in req:
      oldtags=self.Tag.list(page=self.uid)
      newtags=[]
      i=1
      while ('tag%s' % i) in req:
        t=req.get('tag%s' % i)
        i+=1
        if t:
          newtags.append(t)
      for t in newtags:
        self.add_tag(t)# add the tag
      for tob in oldtags:
        tob.delete()

    def delete_branch(self):
        """override of evoke Page.py branch deletion, to include tag deletion
         - deletes self and ALL child pages of any kind (the whole branch!)
         - deletes all related tags also
        """
        for p in self.get_branch():
            if p.kind == 'image':
                self.get(p.uid).delete_image()
            else: 
                # delete related tags
                for t in self.Tag.list(page=p.uid):
                    t.delete()
                # delete page 
                p.delete()

  # ratings + disable/enable ################
  
  downratings=(-4,-4,-3,-2,-4,0,1)
  upratings=(0,-2,-1,-1,1,2,2)

  # access these via rating_symbol()
  ratingsymbols=('&times;','?','&radic;','&hearts;','?','&radic;','&hearts;')

  def rating_symbol(self,rating=None):
    "give symbol for rating"
    # rating should be in (-4,-3,-2,-1,0,1,2)
    r=min(6,max(0,(rating if rating is not None else self.rating)+4))
    return self.ratingsymbols[r]

#  def rating_title(self):
#    "give title for rating"
#    # rating should be in (-4,-3,-2,-1,0,1,2)
#    r=min(6,max(0,self.rating+4))
#    return ('trash','disabled okay','disabled like','disabled love','okay','like','love')[r]
    
  def set_rating(self,rating):
    "sets self.rating to req.rating"
    self.rating=rating
    self.flush() 

#  def minrating(self):
#    "returns minimum rating accepted by global (page 1) and local (self) filters"
#    uid=self.uid if self.kind in self.ratingfilterkinds else 0 # uid containing local filter
#    return self.max('rating',isin={'uid':(1,uid)})

  def minrating(self):
    "returns minimum rating accepted by global filter"
    return self.get(1).rating

  def set_global_filter(self,req):
    "sets root rating (used as a global filter) to req.rating"
    self.get(1).set_rating(req.rating)
    return self.rating_return(req)

  def rate_up(self,req):
    """increase rating 
      - optional req.view gives a redirect function name 
        eg 'playing' (via self.rating_return())
    """
    try:
      self.rating=self.upratings[self.rating+4]
      self.flush()
      self.log_track(self.uid,'rated',self.rating)
    except:
      pass
    return self.rating_return(req)
      
  def rate_down(self,req):
    """decrease rating 
      - optional req.view gives a redirect function name 
        eg 'playing' (via self.rating_return())
    """
    try:
      self.rating=self.downratings[self.rating+4]
      self.flush()
      self.log_track(self.uid,'rated',self.rating)
    except:
      pass
    return self.rating_return(req)

  def toggle_disable(self,req):
    ""
    try:
      self.rating=(0,0,1,2,-3,-2,-1)[self.rating+4]
      self.flush()
      self.log_track(self.uid,'rated',self.rating)
    except:
      pass
    return self.rating_return(req)

  def rating_return(self,req):
    "common return for all re-rating options"
#    if self.uid==1 and self.player.list: # if active play order
#      return self.get(1).play(req) # restart the playlist, re-filtered
    return self.redirect(req,req.view)


  # score (plays) #################################
  
  def score_symbol(self):
    ""
    return str(self.score)
    
    # was...
    if self.score<=0:
      return "!"
    elif self.score>=80:
      return '&starf;'
    elif self.score>=20:
      return '&star;'
    return '&Star;'
 
  def fetch_plays(self,logfiles=[]):
    "get SCORES (plays) AND RATINGS from log file, and store in Play instances and in Pages - called from add_logs() below"
    #format line sample: 7 played at 11/06/2013 15:06:30 *22
    ln=0
    fails=0
    playuid=0
    for logfile in logfiles:
      f=open(logfile,'r')
      log=f.read().split('\n')
      print("LOG ITEMS=",len(log))
      validated=False
      for i in log:
        vals=i.split()
        if len(vals)>4: # otherwise we have an empty or invalid line, so skip it
          if len(vals)==5: # original format
            uid,act,dummy,date,time = i.split()
            val=1
          else: # current and mphistory format
            uid,act,dummy,date,time,val = vals
            if val[0]=='*': # mphistory version
              val=safeint(val[1:])
            else: # current version
              val=safeint(val)  
          if act.startswith('skip'): 
            #val=-val  # THIS IS WRONG - AS val IS ALREADY NEGATIVE FOR SKIPS...
            val=0  # we are not using skips now in the score (VUZ 18/3/2015)
          # check validity
          page=safeint(uid)
          when=DATE(date+" "+time)
          if (act!='rated') and (not validated): # crude but reasonably effective... 
            if self.Play.list(page=page,when=when,times=val): 
              print("duplicate log: %s" % (logfiles[ln],))
              fails+=1  
              break
            validated=True  
          # log it in plays (if it is a play not a skip)
          if act.startswith('play'):
           if self.list(uid=page): # make sure it still exists...
            self.get(page).add_play(when,val)
#            ob=self.Play.new()
#            if not playuid:
#              playuid=ob.uid # first new uid - passed to set_scores() to make it only use the newly added play logs          
#            ob.when=when
#            ob.page=page
#            ob.times=val
#            ob.flush()
#            print 'line ',ln,' uid=',ob.uid,'score=',ob.score
          elif act=='rated': # update Pages ratings crudely - i.e. REGARDLESS OF ANY POSSIBLE MORE RECENT CHANGE HAVING BEEN MADE...
            try:
              pob=self.get(page)
              pob.rating=val
              pob.flush()
            except:
              print("could not find page %s" % page)
              pass # we don't care if the page no longer exists....
      ln+=1
 #   if  playuid:
 #     self.set_scores(playuid)  # updates Pages based on Plays
    print("=== %s logs fetched successfully, %s log duplicates ignored ===" % (ln,fails))
    msg="%s logs processed, %s duplicates ignored" % (ln,fails)
    return msg

  def add_play(self,when,times):
    "adds a play log for self, and adds the play/skip to the score for self"
    # add the play to plays table
    ob=self.Play.new()
    ob.when=when
    ob.times=times
    ob.page=self.uid
    ob.flush()
    # add to score
    self.score=self.score+times
    self.flush()


  @html
  def play_history(self,req):
    "show plays and play log history for this track"
    pass

  @html
  def recent(self,req):
    "list 200 recent track plays (all tracks, from play log, latest first)"
    # fetch the plays
    req.data=[]
    for play in self.Play.list(orderby='`when` desc',limit=page(req,200)):
      try:
        ob=self.get(play.page)
        ob.played=play.when 
        req.data.append(ob)
      except:
        pass  # track has presumably been deleted  
 
  # preferences ###################################
 
  # adopt the standard page preferences, and extend them
  # {kind:{name:(default,display-name,display-type/size/options),},}
  basePage.default_prefs.update((
   ('artists',copy(basePage.page_default_prefs)),
   ('playlists',copy(basePage.page_default_prefs)),
   ('genres',copy(basePage.page_default_prefs)),
   ('playlist',copy(basePage.page_default_prefs)),
   ('artist',copy(basePage.page_default_prefs)),
   ('album',copy(basePage.page_default_prefs)),
   ('track',copy(basePage.page_default_prefs))
   ))
  basePage.default_prefs['track'].update({
  'starttime' : (0,'start time (secs)',4),
  'stoptime' : (0,'stop time (secs)',4),
  'volume' : (100,'volume %',3)
  })
  basePage.default_prefs['album'].update({
  'volume' : (100,'volume %',3)
  })
  basePage.default_prefs['album']["order_by"]=('seq','order items by',('date','latest','name','seq')) # override the default
  basePage.default_prefs['artist']["order_by"]=('score','order items by',('score','date','latest','name','seq')) # score added as default
  basePage.default_prefs['artists']["order_by"]=('score','order items by',('score','date','latest','name','seq')) # score added as default
  basePage.default_prefs['admin']={
  'order_by':('score','album display order',('score','artist','name','date','latest','uid')),
  'theme':('dark','display theme',('light','dark'))
  }
  #basePage.default_prefs['smartlist']=({
  #'order_by':('','order by',('','artist','name','date','latest','score','rating')),
  #'min_rating':('0','minimum rating',('2','1','0','-4')),
  #'max_rating':('2','maximum rating',('2','1','0','-4')),
  #})



  # theme  ################

  def theme_url(self,):
    "override theme_url - CACHED"
    if not hasattr(self,"_theme_url"):
      self._theme_url="/site/theme_%s" % self.get(2).get_pref("theme")
    return self._theme_url


  def change_theme(self,req):
    ""
    os.unlink("../htdocs/site/theme")
    os.symlink("theme_%s" % req.theme,'../htdocs/site/theme')    



  # media player ######################################
  #

  # set up media player
  player=vlc.MediaListPlayer()

  player.autolist=8361 # O/S this is a bodge for one database.. should be using a preference
    # --- OR the above playlist should have a fixed number eg 5

  transport=vlc.MediaPlayer()
#  transport.audio_output_set("pulse") # doesn't work... returns 0
  transport.uid=False  # this will store the uid of the currently playing track
  transport.prevuid=False    # this will store the uid of the previous track played (if any)
  transport.nextuid=False    # this will store the uid of the next track to be played (if any)
#  transport.tracks=0 # this will store the size of the current playlist
  transport.newtrack=False # this will indicate a track change
  transport.log_skip=True # flag to allow logging of skips 
  transport.log_play=True # flag to allow logging of plays 
  player.set_media_player(transport) # associate the transport with the player
  player.set_playback_mode(0) # enforce the default (rather than loop or repeat)
  
# note  I attempted to set volume here...
#
#  transport.audio_set_volume(20) # ie 20%
#  print "volume is:", transport.audio_get_volume()
#  
# note  transport.audio_set_volume(v) DOESN'T WORK!!! - the volume remains at 100% regardless of the value of v
#       Interestingly, transport.audio_get_volume() will return v correctly (i.e. what was set)
#       Also, where v is 0 it DOES work! Otherwise it always gives 100% volume, regardless of v...
#
# UPDATE - actually it does work - it is setting the app volume as per pulseaudio, but my pulseaudio setup is bodged
#       in way that gives me top quality sound through my USB Transit by (somehow) byassing the pulseaudio app volumes!
# 	So, pulseaudio is the culprit!!!
#
#       Is "volume" a discontinued feature?
#       cvlc at the command line, says "--volume no longer exists" !
#       They now use "--gain" eg "--gain=0.2" which works in cvlc, but not as an option for instance.media_new()...
#       There are also various cvlc / vlc options for "audio_replay_gain_???", i.e. uniform volume per track / album...
#       There are no functions for "gain" in vlc.py . Is it just out of date?

  player.list=None  # once set, will be the current list of vlc media items - eg: player.list[0].get_mrl() will give url of track 0 in the list
  player.mode= 0 # default - not looping or repeating
  player.stop() # this seems to fix VLC no-sound glitch on startup...
  # set up our cached states, which will be maintained by get_player_state() and pause()
  player._state="stopped"
#  player.is_shuffling=False # DEPRECATED
  player.is_paused=False
  player.timeleft=True # for tracktime display: False will give time elapsed, True gives time remaining
  player.overviewing=False # display flag - see def toggle_view(), overview() and view()
  # get instance, for general use 
  instance=player.get_instance()


  def prepare_media(self):
    """prepare a media obj for adding to medialist - handle start and stop times
    """
    start=self.get_pref('starttime')
    stop=self.get_pref('stoptime')
##    volume=limit(self.get_pref('volume'),0,200) # use limit() to ensure that volume pref is sensible...
    m=self.instance.media_new(self.mrl())
# NONE of the following options work
#    m=self.instance.media_new(self.mrl(),'gain=0.2')
##    m=self.instance.media_new(self.mrl(),'sout-raop-volume=%s' % volume)
#    m=self.instance.media_new(self.mrl(),'audio-replay-gain-mode=track','--audio-replay-gain-default=0.2')
    if start:
        m.add_options('start-time=%s' % start) 
    if stop:
        m.add_options('stop-time=%s' % stop) 
# the following test code DOES NOT WORK, though it does in cvlc at the command line, eg > cvlc my.mp3 --gain=0.2
#    gain="1.5"
#    print "SETTING GAIN for %s at %s%%" % (self.uid,gain)
#    m.add_option('gain=%s' % gain)
    return m

  def get_state(self):
    "get VLC state data about currently playing item - DO WE NEED THIS FOR ANYTHING?"
    states={
     vlc.State.Buffering:"buffering",
     vlc.State.Ended:'ended', 
     vlc.State.Error:'ERROR',
     vlc.State.NothingSpecial:"ok",
     vlc.State.Opening:"opening",
     vlc.State.Paused:"paused",
     vlc.State.Playing:"playing",
     vlc.State.Stopped:"stopped",
     }
    if self.player.list:
      state=states.get(self.transport.get_media().get_state(),"other")
    else:
      state="off"
    return state


  def get_player_state(self):
    "get our required state info: 'stopped', 'playing', 'paused', or 'ended'"
    # here is how to identify the 4 listplayer states that we care about:
    # - stopped:  (not self.player.list)
    # - playing:  self.player.list and self.player.is_playing()
    # - paused:   self.player.list and self.player.is_paused
    # - ended:    self.player.list and not (self.player.is_playing() or  self.player.is_paused)
    #note: player.is_paused is set by def pause()
    #note: we don't want the 'ended' state, so we will 'stop' ASAP - see newtrack() 
    if self.player.list:
        if self.player.is_playing():
          s='playing'
        elif self.player.is_paused:
          s='paused'
        else:
          s='ended'  
    else:
        s='stopped'
    return s


  def uid_now_playing(self):
    "give uid of currently playing track from the transport"
##     - brute force method required in absence of functioning callbacks.... WORKS but not required now we know about transport
#    current=0
#    for i in self.player.list:
#      if i.get_state() in (vlc.State.Buffering,vlc.State.Opening,vlc.State.Paused,vlc.State.Playing,vlc.State.Stopped):
#        current=i.get_mrl()
#        current=current.rsplit("/",1)[1][:-4]
#        break
#    return safeint(current)
    self.transport.media=self.transport.get_media()
    if self.transport.media:
        mrl=self.transport.media.get_mrl()
#        print ">>>>>>>>>>>>>>>",mrl 
        return safeint(mrl.rsplit("/",1)[1].rsplit(".",1)[0]) # extract the uid as text, and convert to int
    return 0

  def next_up(self):
    "uid of next track on playlist (if any)"
    nup=False
  #  print "self.transport.uid= ",self.transport.uid
  #  print "self.player.is_paused= ",self.player.is_paused
    uid=self.transport.uid
    if uid:
        playlist=self.get(1).text.split('\n')
        try:
            p=playlist.index(str(uid))
        except:
            p=-1
        if (p>=0) and ((p+1)<len(playlist)):
            nup=safeint(playlist[p+1])
    return nup

  def prev_played(self):
    "uid of last-played track (from play log)"
    try:
      logged=self.Play.list(orderby='`when` desc',limit="1")[0]
      pp=logged.page
#      print ">>>>>",pp
    except:
#      raise
      pp=False 
    return pp

  def set_transport_uids(self,uid):
    "maintain info on previous, current, and next track - cached in self.transport"
    t=self.transport
    # set previous uid
    t.prevuid=self.prev_played()
    # set current uid regardless (as may be False, which is valid)
    t.uid=uid
    # set next uid
    if t.uid:
      t.nextuid=self.next_up()
    return True

  # automated display 

  def auto(self,req):
    """auto-show the currently-playing track

    - redirects recursively to the currently playing track, then returns view() for that track
    - forces a stop when playlist is finished, and returns to playlist page
    - if already stopped, will start autoplay when self is the default autoplay playlist

#    - req.over - if True, forces overview mode
    - sets req.auto to the currently playing track
    """
#    if req.over:
    self.player.overviewing=True # allow forcing of overview
    if self.player.is_playing():
      # get currently playing track object, and store the uid in self.transport.uid"
      self.set_transport_uids(self.uid_now_playing())
      # store the currently-playing track object as req.auto
      req.auto=self.get(self.transport.uid)
      # if self is the current track or album, then return self.view()
      if (req.auto.uid==self.uid) or (self.kind=="album" and (self.uid==self.player.list.uid)):
        req.return_to=self.url("auto")
        return self.view(req) # update the track or album display
      # otherwise recurse to show the currently playing track
      return req.auto.redirect(req,"auto") 
    elif self.player.is_paused:
      return self.get(self.player.is_paused).redirect(req) # show the currently paused track
#   if we get here, then presumably the player has stopped...
    # start playing autolist, if requested..
    if self.uid==self.player.autolist:
      return self.get(self.player.autolist).redirect(req,"play")
    # otherwise, show "from" playlist 
    frm=self.player.list.uid if self.player.list else 1
    return self.get(frm).redirect(req,"")

  def view(self,req):
    "custom default view (override of basePage.view())"
    # flag whether page should be refreshed when track changes 
    # - ie whether self is the current track or album or artist
    cuid=self.transport.uid
    uids=(cuid,1,self.player.list.uid) if self.player.list else (cuid,)
    req.refresh=self.uid in uids
#    print "req.refresh:",req.refresh
    # get req.data if necessary
    if self.kind in self.playlistkinds:
      req.data=self.get_playlist_section(req,)
    # check album length, if an album
    # - Brute force approach for certainty...
    # - This covers track additions, deletions, and moves...
    if self.kind=='album':
      self.check_album_length()
    elif self.kind=="playlist":
      self.set_length()
    # similar for score (play totals net of skips) for artists and albums
    if self.kind in ('album','artist'):
      self.update_score()
    # return the appropriate display
    if self.player.overviewing:
      return self.overview(req)
    return basePage.view(self,req)

  def time_left(self):
    """gives time remaining for the current track (not necessarily self) in milliseconds
       - allows for override by "stoptime" preference (stored in self.transport.stoptime)
      """
    t=self.transport
    return (t.stoptime or t.get_length())-t.get_time()

  def toggle_view(self,req,method=''):
    "toggles between overview and view modes"
    self.player.overviewing=not self.player.overviewing
    return self.redirect(req,method) # this will redirect to self.overview(req) if overviewing 

#  def toggle_auto(self,req):
#    "toggles between overview and view playing modes"
#    return self.toggle_view(req,'auto') 


  @html
  def track_overview(self,req):
    ""
#    req.wrapper="wrapper_subtle.evo"
 
  @html
  def album_overview(self,req):
    ""
#    req.wrapper="wrapper_subtle.evo"

  @html
  def artist_overview(self,req):
    ""
    req.data=self.get_artist_playlist

  def overview(self,req):
    "track/album overview"
    if not self.player.overviewing: # ensure that we are in the correct mode...
      return self.toggle_view(req)
    if self.kind=='artist': # fetch the artis
      return self.artist_overview(req)  
    elif self.kind=='album': # fetch the album
      return self.album_overview(req)  
    elif self.kind=='track': # fetch the track
      return self.track_overview(req)
    # anything else...
    return basePage.view(self,req)

#  @html
#  def album_select(self,req):
#    "album selection by thumbnail"
# #   req.wrapper="wrapper_subtle.evo"
#    prefob=self.get(2) # preferences for this are stored in page 2
#    req.data=self.list(kind='album',where='rating>=%s' % prefob.get_pref('min_rating'),orderby=prefob.get_order())
#    req.title="albums"

  @html
  def albums(self,req):
    "album listing by score or whatever"
    prefob=self.get(2) # preferences for this are stored in page 2
    limit=page(req)
    req.pages=self.list(kind='album',where='rating>=%s' % self.minrating(),orderby=prefob.get_order(),limit=limit)
    req.title=req.page="albums"
#    print ">>>>>>>>>>>>>>>>>", req.page, req.pagesize, len(req.pages)



  # AJAX handlers

  def toggle_time_display(self,req):
    "toggle between time remaining (left) and time elapsed"
    self.player.timeleft = not self.player.timeleft
    return ""  # result of this function is not used
    
  def tracktime(self,req):
    "AJAX handler - returns formatted string showing current track-time (elapsed or remaining)"
    def formatted(ms):
        "formats milliseconds in minutes and seconds"
        if ms<0:
          return "-:--"
        s=ms//1000
        m,s=divmod(s,60)
        return "%d:%02d" % (m,s)
    left=self.time_left()
    if left<2000 and left>0: # flag that a trackchange is approaching
      self.transport.newtrack=True
#      print "--------- newtrack flagged ------ %s left------" % left
    t="%s" % formatted(left if self.player.timeleft else self.transport.get_time())
 #   print ">>>> tracktime poll - time remaining:",t
    return t
       
  def trackchange(self,req):
    "AJAX handler - returns 'yes' when there has been a track change, or playlist is ended, requiring a page refresh"
    if self.newtrack():
  #    print "========= refreshing..."
      return "yes"
#    print "====== poll trackchange again in %s ms" % max(self.time_left(),2000)      
    return str(max(self.time_left(),2000))  # poll again in 2 seconds or later (when we think the track will be ended)
    
  def bgtrackchange(self,req):
    "AJAX handler - logs background track change - returns milliseconds until next check"
    self.newtrack() # we don't care about the result
#    print "============ poll bgtrackchange again in %s ms" % max(self.time_left(),2000)      
    return str(self.time_left())

  def store_newtrack_data(self):
    "updates self.transport properties after a track change"
    # recognise the track change by clearing the "newtrack" flag
    self.transport.newtrack=False 
    # update the current uid
    uid=self.uid_now_playing()
    self.set_transport_uids(uid)
    # calculate and store stoptime - so we can allow for any track "stoptime" preference
    self.transport.stoptime=safeint(self.get(uid).get_pref("stoptime"))*1000
    return True

  def newtrack(self):
    "does common handling for a track change" 
    playing=self.player.is_playing()
    changed=self.transport.newtrack and (self.time_left()>=2000)
    if self.transport.uid and (changed or not playing):
      # the track has changed....
      # print "======= track change - changed=%s, uid=%s, now=%s\n" % (changed, self.transport.uid, self.uid_now_playing())
      # log the (old i.e. previous) track
      self.log_track(self.transport.uid)
      if playing:
        # update self.transport properties for the new track - this also resets our "newtrack" flag
        self.store_newtrack_data()
      elif not self.player.is_paused: # presumably we are at the end of the playlist, so force a stop
        # print "stopping......"
        self._stop()
      return True
    # print "======= polling for track-change \n",
    return False

# old version - works, but complex
#
#  def newtrack(self):
#    "does common handling for a track change" 
#    playing=self.player.is_playing()
#    repeating=self.transport.newtrack and ((self.player.mode==2) or (self.player.mode==1 and self.transport.tracks==1)) and (self.time_left()>=2000)
#    if self.transport.uid and ((self.transport.uid!=self.uid_now_playing()) or repeating or not playing):
#... same from here on



  # play / skip logging

  def log_track(self,uid,action='played',times=0):
    "logs an action for the given track uid"
    # abort if play-order or if use of forward or back buttons has disallowed logging 
    if uid==1:
      return 
    elif action=='played' and not self.transport.log_play:
      return
    elif action=='skipped' and not self.transport.log_skip:
      return  
    self.transport.log_skip=True # re-allow logging of skips 
    self.transport.log_play=True # re-allow logging of plays 
    # do the logging
    when=DATE().time(sec=True)
    if not times:
      if action.startswith('played'):
        times=1
      elif action.startswith('skipped'):   
        times=-1
    logfile=open('../logs/mp.log','a')
    logfile.write("%s %s at %s %s\n" % (uid,action,when,times))
    logfile.close()
    # add to plays and tracks (skips are ignored)
    if action!='rated' and times>0:
      self.get(safeint(uid)).add_play(when,times)  
#    print "%s %s at %s\n" % (uid,action,DATE().time(sec=True))

  def log_skip(self,back=False):
    """ignore if in first 2% of the track, otherwise:
       - log a skip if in first half of track and skipping forward. 
       - log a play if in last half.
       """
    self.transport.newtrack=False # reset the flag, just in case
    percent=(self.transport.get_time()*100)//self.transport.get_length()
    uid=self.transport.uid
    if uid:
      if (not back) and (percent>2) and (percent<50):
        self.log_track(uid,'skipped-%s%%' % percent)   
      elif (percent>=50):
        self.log_track(uid,'played-%s%%' % percent)   

  def log_play(self):
    "log a play if more than half way through"
    self.log_skip(back=True)

  def log(self,req):
    "for manually adding a play..."
    if self.kind=='track':
      self.log_track(self.uid,'played-?%')
    else:
      req.error="can only log a play for a track"
    return self.get(self.uid).view(req) # refetch to get updated plays

#  # event callback for track change
# CALLBACKS DO NOT WORK HERE (though they work fine in an unthreaded test program)- presumably because of Twisted threading

#  from twisted.internet import reactor
  
#  def event_next_item(event):
#    ""
##    pass
#    print "............................... next item", event

#  print type reactor.callFromThread(event_next_item, 3)
#  player.event_manager().event_attach(vlc.EventType.MediaListPlayerNextItemSet,event_next_item)
##  player.event_manager().event_attach(vlc.EventType.MediaListPlayerPlayed,event_played)
##  player.event_manager().event_attach(vlc.EventType.MediaListPlayerStopped,event_stopped)


  # transport

  def mrl(self):
    "get the audio file url ('media resource locator')"
    return str(self.file_loc(self.code))

  def get_index(self):
    "return the index (within self.player.list) of the currently playing item"
    m=self.transport.get_media()
    pos=self.player.list.index_of_item(m)
    return pos

  def goto(self,req):
    "jumps to given req.index (which is required) - used by playlist displays"
    if self.player.list and req.index:
      self.log_play()
      if self.player.play_item_at_index(safeint(req.index))==0: # if found the item
        self.player.is_paused=False
    return self.redirect(req,"auto")

  def play(self,req):
    "starts playing a new list"
    if self.kind in self.playablekinds:   
      # kill any existing vlc list (just in case)
      if self.player.list:
        self.log_play()
        self._stop()
      # load new playlist into vlc  
      # 1) create a new vlc playlist
      self.player.list=vlc.MediaList()
      # 2) populate it with our track url(s)
      self.player.list.lock()
      playlist=self.get_playlist()
      for i in playlist:
        self.player.list.add_media(i.prepare_media())
      self.player.list.unlock()
      # 3) publish it to the player
      self.player.set_media_list(self.player.list)
      self.player.list.uid=self.uid # store where the playlist came from
      # 4) and play!
      self.player.play()
      #save playlist in root
      root=self.get(1)
      uids=[str(i.uid) for i in playlist]
      root.text="\n".join(uids)
      root.flush()
      # update self.transport properties for the new track
      self.store_newtrack_data()
      # and return
      self.player.overviewing=True # force to overview mode
      return self.redirect(req,"auto")
    req.error='unable to play this item'  
    return self.view(req)

  def playnext(self,req):
    "add self to playlist as next item - a simple LIFO stack"
    if not self.player.list:
      return self.play(req) # this creates a new medialist
    # find the current index position in medialist (this may get it wrong if there are duplicates... but what to do??)
    root=self.get(1)
    rootuids=root.get_dumb_playlist()
    ix=self.get_index()+1 # this should point to after the currently playing track
    sx=ix # save the starting index - we need it below
    # add track or playlist to vlc medialist
    self.player.list.lock()
    playlist=self.get_playlist()
    for i in playlist:
      self.player.list.insert_media(i.prepare_media(),ix)
      ix+=1
    self.player.list.unlock()
    self.player.list.uid=1 # we have a mixed list, so let it be "from" the play order itself
    # update the root playlist, by inserting the new item(s)
    uids=rootuids[:sx]+[i.uid for i in playlist]+rootuids[sx:]
    root.text="\n".join([str(i) for i in uids])
    root.flush()
    # and return
    req.message="%s added to play order" % self.name
    if req.return_to:
      return req.redirect(req.return_to)
    return self.redirect(req,"")

  def pause(self,req):
    "pauses and restarts"
    if self.player.is_playing():
      uid=self.uid_now_playing()
      self.player.is_paused=uid
      self.set_transport_uids(uid) # ensure these are correct
      self.player.pause()
    elif self.player.is_paused:
      self.player.play()
      self.player.is_paused=False
      return self.redirect(req,"auto")
#      return self.auto(req)
    elif self.kind in self.playablekinds: # we have an out-of-date pause, so play the current page
      return self.play(req)  
    return self.redirect(req,"")

  def _stop(self):
    "stops and clears the list"
    if self.player.list:
      self.player.stop()
      self.player.list.release()
      self.player.list=None
      self.player.is_paused=False
      self.set_transport_uids(False) # indicate that we are not currently playing

  def stop(self,req):
    "stop and clear the list"
    self.log_play() # log track as played if it is more than 2/3 through
    self._stop()
    req.auto=False
    return self.redirect(req,"")

  def forward(self,req):
    "jump forward 10 secs"
    xtime=self.transport.get_time()
    self.transport.set_time(xtime+10000)
    self.transport.no_play=False
    return self.redirect(req,"auto")
#    return self.auto(req)

  def backward(self,req):
    "jump backward 10 secs"
    xtime=self.transport.get_time()
    self.transport.set_time(xtime-10000)
    self.transport.no_skip=False
    return self.redirect(req,"auto")
#    return self.auto(req)

  def skip(self,req):
    "play next track in list"
    self.log_skip()
    # do the skip
    # VLC has a bug (when loop is not set) whereby if you skip the last track, it keeps playing it and then loops! - so we fix that
    xuid=self.uid_now_playing()
    xtime=self.transport.get_time()
    self.player.next() # tell the player to do the skip....
    if self.player.mode!=1: #if not looping
      if (xuid==self.uid_now_playing()) and (xtime<=self.transport.get_time()): #  we must be on the last track, so stop
        self._stop()
    # update self.transport properties for the new track
    self.store_newtrack_data()
    return self.redirect(req,"auto")
#    return self.auto(req)

  def skipback(self,req):
    "play previous track in list"
    self.log_play()
    # do the skip
    # VLC has a bug (when loop is not set) whereby if you skipback the first track, it keeps playing it and then repeats it! - so we fix that
    xuid=self.uid_now_playing()
    xtime=self.transport.get_time()
    self.player.previous()  # tell the player to do the skip....
    if self.player.mode!=1: #if not looping
      if (xuid==self.uid_now_playing()) and (xtime<=self.transport.get_time()): #  we must be on the first track, so stop
        self._stop()
    # update self.transport properties for the new track
    self.store_newtrack_data()
    return self.redirect(req,"auto")
#    return self.auto(req)

# global playlist shuffle toggle NOW REPLACED BY "shuffle and play"
#  def shuffle(self,req):
#    "toggle shuffle mode"
#    self.player.is_shuffling=not self.player.is_shuffling
#    if self.player.list:
#      return self.get(self.player.list.uid).play(req) # restart the playlist, newly shuffled or not (as the case may be)
#    return self.view(req)  

  def shuffle(self,req):
    "shuffle and play"
    self.shuffling=True
    return self.play(req)  

  def loop(self,req):
    "toggle loop mode (to loop/unloop the entire play order)"
    if self.player.mode==1:
      self.player.mode=0 #vlc.PlaybackMode.default
    else:
      self.player.mode=1 #vlc.PlaybackMode.loop
    self.player.set_playback_mode(self.player.mode)
#    return self.redirect(req,"auto")
    return self.redirect(req)

  def repeat(self,req):
    "toggle repeat mode (to loop/unloop a single track)"
    if self.player.mode==2:
      self.player.mode=0 #vlc.PlaybackMode.default
    else:
      self.player.mode=2 #vlc.PlaybackMode.repeat 
    self.player.set_playback_mode(self.player.mode)
    if self.transport.uid:
      return self.redirect(req,"auto")
  #    return self.auto(req)
    return self.view(req)

  def get_track_data(self,path=""):
    "returns a dict of track meta data"
    filename=path or self.file_loc(self.code)
    media=vlc.Media(str(filename))
    media.parse()
    d=[str(media.get_meta(i) or "") for i in range(17)]
    length=media.get_duration()//1000
    size=os.stat(filename).st_size
    try:
      density=size//length  # very rough, as length includes the file header!
    except: # for some reason length is occasionally 0, giving divide by zero error....
      density=0
    data={
     'name':d[0],
     'artist':d[1],
     'genre':d[2],
     'album':d[4],
     'seq':d[5],
     'text':d[6],
     'when':d[8],   
     'arturl':d[15],
     'length':elapsed(length),          
     'size': size,
     'lossless': density>70000, #>100000 was failing...
     }
    media.release()
    return data
 
  @html   
  def view_filedata(self,req):
    "show track file data on a separate page"
    req.data=self.get_track_data()

  def display_length(self,format="m:s"):
    ""
    return elapsed((self.length+500)//1000,format=format)

  def set_length(self):
    '''set length for self, if relevant (i.e. a track or an album or a playlist)
    SLOW for tracks - this is why we store length separately
    '''
    if self.kind=='track':
      xlen=self.length
      filename=self.file_loc(self.code)
      media=vlc.Media(str(filename))
      media.parse()
      self.length=media.get_duration()
      if self.length!=xlen:
        self.flush()
    elif self.kind=='album':
      xlen=self.length
      self.length=self.sum(item='length',parent=self.uid,kind="track")
      if self.length!=xlen:
        self.flush()
    elif self.kind=='playlist':
      xlen=self.length
      self.length=sum([i.length for i in self.get_dumb_playlist(objects=True)])
      if self.length!=xlen:
        self.flush()

  def check_album_length(self):
    "check/set all child track lengths, and the album total length, for self - self must be an album"
    if self.kind=='album':
      c=0
      tracks=self.list(kind='track',parent=self.uid)
      for i in tracks:
        if not i.length:
          i.set_length()
          c+=1
      self.set_length()  

  def update_score(self):
    "update total score (plays net of skips) for an album or artist"
    xscore=self.score
    if self.kind=='album':
      self.score=self.sum(item='score',parent=self.uid,kind="track")
    elif self.kind=='artist':
      self.score=self.sum(item='score',parent=self.uid,kind="album")
    if self.score!=xscore:
      self.flush()

########## charts ###############################

  @html
  def charts(self,req):
    """ chart display
    expects - req.data - a list of pages with added .plays properties
            - req.title: the name of the chart
            - req._pl_chartkind: the type of chart
            - req._pl_index - index of currently playing song (if relevant)
            - req._pl_len - number of items
            - req._pl_start - index of start of display items
            - req._pl_prevperiod as integer year/month eg 2014 or 201410
            - req._pl_nextperiod ditto
    eg see chart()
    """
    self.player.overviewing=True

  def prevperiod(self,period):
      "return prior integer year/month eg 2014 or 201410"
      if (period>9999) and str(period).endswith('01'):
        return period-89
      elif period:
        return period-1
      return 0

  def nextperiod(self,period):
      "return subsequent integer year/month eg 2016 or 201601"
      if (period>9999) and str(period).endswith('12'):
        return period+89
      elif period:
        return period+1
      return 0

  def get_chart_period(self,req):
    """return required period-related values based on req.period

      if req.period is specified as a year - eg 2014
      then give that year

      elif req.period is specified as an integer-date - eg 201403
      then give that full calender month

      else default to all-time period (ie 20140101 to date) 
    """
    now=int(DATE())
    period=INT(req.period) # allow for it having been a string
    if period>9999: # assume it is a month
      if period<(now//100): # a valid complete month
        prior=True# this is a previous month
      else:
        period=now//100 # default to current month
        prior=False
      start=period*100+1
      end=self.nextperiod(period)*100+1
    else: # assume it is a year
      if period and (period<(now//10000)): # a prior year
        prior=True# this is a previous year
      else:
        period=now//10000 # default to current year
        prior=False
      start=period*10000+101
      end=self.nextperiod(period)*10000+101
    return period,start,end,prior

  def period_chart(self,req,period,start,end,prior):
    """ generic monthly / annual / all-time chart
        expects req._pl_chartkind and self.sql
    """
    # fetch the raw data
    period,start,end,prior=self.get_chart_period(req)
    todate='' if prior else 'to date'
    year=int(str(period)[:4])
    now=int(DATE())
    if req.alltime and (period in (now//10000,now//100)):
        req.title=f"{req.alltime} {req._pl_chartkind}"
    elif period>9999:
        date=DATE(period*100+1)
        req.title=f"{req.alltime} {req._pl_chartkind} for {date.datetime.strftime('%B')} {year} {todate}"
    else:
        req.title=f"{req.alltime} {req._pl_chartkind} for {year} {todate}"
    raw=self.list(asObjects=False,sql=self.sql)
    # process the raw data, so it is ready for the template
    req.data=[]
    for i in raw:
        try:
          ob=self.get(i["page"])
          ob.plays=i["sum(times)"] # monthly score is stored temporarily as self.plays
          req.data.append(ob)
          # is this the currently playing/paused track?
          if self.player.list and (ob.uid == self.transport.uid):
            req._pl_index=ob.uid  # the display will use this to hilite the track 
        except: # we have a deleted item - ignore it
          pass
#      for i in req.data:
#        print(i.uid, i.name, i.times)
    # set more constants for the template to use
    req.period=period
    req._pl_prevperiod=self.prevperiod(period)
    if prior:
      req._pl_nextperiod=self.nextperiod(period) 
    req._pl_len=len(req.data)
    req._pl_start=0
    # and return the template
    return self.charts(req)

  def chart(self,req):
    "monthly or annual track charts"
    req._pl_chartkind=f"chart"
    db=self.Config.database
    period,start,end,prior=self.get_chart_period(req)
    if req.alltime:
        where=f"`when`<'{end}'"
    else:
        where=f"`when`>='{start}' and `when`<'{end}'"
    self.sql=f"""
        select page,sum(times)
        from `{db}`.plays
        where {where}
        group by page having sum(times)>1
        order by sum(times) desc
        limit 500;
        """
    return self.period_chart(req,period,start,end,prior)

  def album_chart(self,req):
    "monthly or annual album charts"
    req._pl_chartkind="album chart"
    db=self.Config.database
    period,start,end,prior=self.get_chart_period(req)
    if req.alltime:
        where=f"plays.`when`<'{end}'"
    else:
        where=f"plays.`when`>='{start}' and plays.`when`<'{end}'"
    self.sql=f"""
        select album.uid as page, sum(times)
        from `{db}`.plays inner join `{db}`.pages on plays.page=pages.uid
        inner join `{db}`.pages as album on album.uid=pages.parent
        where {where}
        group by album.uid having sum(times)>2
        order by sum(times) desc
        limit 500;
        """
    return self.period_chart(req,period,start,end,prior)

  def artist_chart(self,req):
    "monthly or annual artist charts"
    req._pl_chartkind="artist chart"
    db=self.Config.database
    period,start,end,prior=self.get_chart_period(req)
    if req.alltime:
        where=f"plays.`when`<'{end}'"
    else:
        where=f"plays.`when`>='{start}' and plays.`when`<'{end}'"
    self.sql=f"""
        select artist.uid as page, sum(times)
        from `{db}`.plays inner join `{db}`.pages on plays.page=pages.uid
        inner join `{db}`.pages as album on album.uid=pages.parent
        inner join `{db}`.pages as artist on artist.uid=album.parent
        where {where}
        group by artist.uid having sum(times)>2
        order by sum(times) desc
        limit 500;
        """
    return self.period_chart(req,period,start,end,prior)

  def charts_summary(self,req):
    "prepares the data for the charts summary, and returns the template"
    req.title="summary of track plays"
    req._pl_chartkind="charts summary"
    xperiod=req.period
    req.period=int(DATE())//100 # current month
    req.data=[]
    while True:
      # get one year's data
      months=[0]*12
      annual=0
      while True:
        plays=self.monthly_plays(req)
#        print(req.month,' plays = ',plays)
        year=req.period//100
        month=req.period%100
        months[month-1]=plays
        annual+=plays
#        print("year:",year," month:",month," months:",months," annual:",annual)
#        print("type of month: ",type(month))
        req.period=self.prevperiod(req.period)
        if month==1:
          break
      # and add it to req.data 
      if not annual:
        # or (INT(req.month)<201400): # O/S: the 201400 condition is specific to the original IHM dataset, but this should not affect any newer datasets
        break
      req.data.append((year,months,annual))
    # restore the previous req.period
    req.period=xperiod
    # and return the template
    return self.charts(req)

  def monthly_plays(self,req):
    "total plays for req.month - for use by charts_summary() "
    db=self.Config.database
    req.period,start,end,prior=self.get_chart_period(req)
    plays=INT(self.Play.sum(item="times",where=f"`when`>='{start}' and `when`<'{end}'"))
    return plays

######## additions ##################################

  def add_logs(self,req):
    "fetch play log(s) from mp/logs/additions folder, and process"
    logfiles=[]# list of logs
    names=[] #list without paths 
    folder="../logs/additions"
    for name in os.listdir(folder):
      if name.endswith(".log"):
        logfiles.append("%s/%s" % (folder,name))
        names.append(name)
    msg=self.fetch_plays(logfiles)      
    if not msg.startswith('0'):
      for i in names: # move them to logs folder
        os.rename(folder+"/"+i,'../logs/'+i)
    return msg

  def add_music(self,req):
    '''
    fetch new music from mp_additions folder, and allocate to new/existing albums/artists
        
    - assume that self.Config.additions_folder (default = "mp_additions") will hold any new audio files to be added
    - fetch (move) whatever audio files are there (including in subfolders) 
    - for each one:
      - new track page for every audio file (temporarily put them all  in untitled album in Compilations)
      - audio file is renamed and moved to data folder
      - get track meta-data
      - if there is artwork, add the image
      - if there is a genre, add that
    - finds a sensible place for each track, by analysing them:
      - if by existing album artist, add them there
      - elif got 2 or more with same album, and artists differ, then  add that album (if necessary) in Compilations, and put them there
      - elif got 2 or more with same album and artist, then add that album and artist, and put them there
      - anything left will remain in the untitled album in Compilations  
    '''
    # fetch some key data objects..
    hob=self.get(3) # get the parent page for the artists
    cob=self.get(4) # get the Compilations pseudo-artist (our default place for the new tracks)
    dobs=self.list(parent=4,name='',kind='album')  # get the default album - the untitled album in Compilations
    if dobs: # we have the default album
      dob=dobs[0]
    else: # we create it
      dob=cob.add_album("")
    additions=[]# list of new tracks and their given albums 
    # get a list of filepaths, extract audio files, create tracks for them, moving the files to the ~/data folder
    for path,dirs,files in os.walk(self.Config.additions_folder):
      #print path,dirs, files
      for name in files:
        exts=name.rsplit(".",1)
        if (len(exts)==2):
          ext=exts[1].lower()
        else:
          ext=""
        if ext in ('mp3','m4a','flac','wav','xm','dts','mts','ogm','ogg','a52','aac','ac3','oma','spx','mod','mp2','wma','mka','m4p'):
          # create track
          r=Req()
          r.kind='track'
          r.stage='posted'
          tob=dob.create_page(r)
          # get the meta (before we move the file, as vlc may use the old filename for info)
          filepath=path+'/'+name
          data=tob.get_track_data(path=filepath)
          # move & rename audio file
          tob.code= "%s.%s" % (tob.uid,ext)
          os.renames(filepath,tob.file_loc(tob.code)) #BEWARE: this will remove the mp_additions folder itself if it is now empty...
  #        tob.flush() # store the new code
  #        print tob.uid," === ",data
          tob.name=data['name']
          tob.artist=data['artist']
          tob.seq=safeint(data['seq'])
          tob.text=data['text']
          if 0<safeint(data['when'])<10000: # got the year
            tob.when="1-1-%s" % data['when']
          # store it all
          tob.flush()
          # get length
          tob.set_length() 
          # store genre, if valid
          if data['genre'] and (data['genre'] in self.get_tagnames()):
            tob.add_tag(data['genre'])
          # add to additions list
          tob.album=data['album'] # store this in tob, for now 
          tob.arturl=data.get('arturl')
          additions.append(tob) 
    # now relocate tracks to album and/or artist, as required       
    # split by album:
    albums={}
    for tob in additions:
      if albums.get(tob.album):
        albums[tob.album].append(tob)
      else:
        albums[tob.album]=[tob]
    # process by album
    for album,tobs in list(albums.items()):
      ok=True
      artist=tobs[0].artist
      mob=None # album object (may be set below)  SHOULD IT NOT ALWAYS BE SET?????
      for tob in tobs[1:]:
        if tob.artist!=artist:
          # differing artists, so leave in compilations
          ok=False
      if ok : # we have one album, one artist
        # look for the artist
        aob=None
        aobs=self.list(name=artist,kind='artist') 
        if aobs: # got it
          aob=aobs[0]
        elif len(tobs)>1:  # add it
          aob=hob.add_artist(artist) # create new artist
        if aob: # we have an artist, and 2 or more tracks...
          mob=aob.add_to_album(album,tobs) # add tracks to the album (creating album if required)  
      elif album:# we have one album, more than one artist
#        if len(tobs)==1:
#          album="" # force use of untitled when we only have one track... 
        # add it to the Compilations artist (creating album if required)  
        mob=cob.add_to_album(album,tobs)
      #(otherwise, we leave the track(s) where they are) 
      # get the images (if any)
      for tob in tobs:
        url=tob.arturl
        if url and (url!='None') and url.startswith("file"):
          path= urllib.request.url2pathname(url)[7:]
          if album: # add one image to the album
            if mob and not mob.get_images():
              mob.add_art(path,"500")
            break #we only want one
          tob.add_art(path) # no album, add every track image
    # return some useful info
    if additions:
      req.message="%s tracks added" % len(additions) 
      req.additions=[i.uid for i in additions] #this will be used to hilite the new items in the display
      # set global filter to 0 if necessary - so that the additions are displayed
      ob=self.get(1)
      if ob.rating>0:
        ob.set_rating(0)
#    else:
#      req.warning="no new additions found"
    pl=self.list(parent=2,name='additions',kind='smartlist')
    if pl:
      return pl[0].view(req)
    req.warning=" 'additions' playlist not found"
    return self.view(req)          


  def add_to_album(self,album,trackobs):
    ''' adds a list of track objects to a named album, creating it if necessary 
    - returns the album object
    - self must be the album artist
    ''' 
    # look for the album  
    mobs=self.list(name=album,parent=self.uid,kind='album')
    if mobs: # got it
        mob=mobs[0]
    else: # add it  
        mob=self.add_album(album)
    # move the tracks to the album
    for tob in trackobs:
        tob.parent=mob.uid
        tob.set_lineage(mob)
        tob.flush()
    # set the album length
    mob.set_length()
    return mob

  def add_artist(self,name):
    "adds a new album artist to self"
    req=Req()
    req.kind='artist'
    req.name=name
    req.stage='posted'
    req.parent=self.uid
    req.rating=0
    req.code=''
    req.seq=0
    req.text=''
    aob=self.create_page(req)
    aob.set_pref('order_by','name')
    aob.flush()
    return aob
  
  def add_album(self,name):
    "adds a new album to self"
    req=Req()
    req.kind='album'
    req.name=name
    req.artist=self.name
    req.stage='posted'
    req.parent=self.uid
    req.rating=0
    req.code=''
    req.seq=0
    req.text=''
    aob=self.create_page(req)
    aob.set_pref('order_by','seq')
    aob.flush()
    return aob

  def add_art(self,path,size="500"):
    """ adapted from image_saved() in base/Page.py
    
    stores new image, and returns image object, else returns None 
    """
    error=False
    if path:
      print("processing %s to %s" % (path,self.uid))
      f=open(path,'r') 
      filedata=f.read()
      extension=(imghdr.what('',filedata) or path.rsplit(".")[-1].lower()).replace('jpeg','jpg')
      if not filedata:
        error= "NO IMAGE FOUND AT '%s'" % path
        print(error)
      elif extension in ('bmp','png'):
        filedata=self.Image.convert(filedata)
        extension='jpg'   
      elif extension not in ('gif','png','jpg','jpeg'):
        error="only JPEG, GIF, PNG, and BMP are supported"
        print(error)
      if not error:
        # create a new image page
        image=self.Image.new()
        image.parent=self.uid
        image.kind='image'
        image.seq=0xFFFFFF#place at end of siblings
        # set default size 
        image.stage='right full %sx%s' % (size,size) #rest of stage data will be added on the fly later by get_stage_data() 
        image.set_lineage()
        image.code="%s.%s" % (image.uid,extension)
        image.when=DATE()
        image.flush() #store the image page
        image.renumber_siblings_by_kind()#keep them in order
        # save the image file
        image.save_file(filedata)
        # return
        print('image "%s" added' % image.code)
        return image
    return None


####### search extensions ####################

  @classmethod
  def search_extra_objects(cls,term):
    "include new columns and tags in search"
    obs=cls.list(where='artist like "%%%s%%" or composer like "%%%s%%"' % (term,term),orderby='uid desc')  
    tobs=[cls.get(i.page) for i in cls.Tag.list(name=term, orderby='uid desc')]
    return obs+tobs

######## utilities #################################

  @classmethod
  def halt(self,req):
    "forces the system to quit"
    reactor.callFromThread(reactor.stop)
    return 'system halted'

  @classmethod
  def clone_data(self,req):
    """clones all music data from req.source to req.dest
     O/S should first pull in and set up the mp code and music db (DO THIS MANUALLY for now)
    """
    # source folder
    source=req.source or "/media/howie/archive/data/music/"
    # destination folder
    dest=req.dest or "/home/howie/data/music/"
    # clone the music files
    c=0
    for i in self.list(isin={'kind':("track","image","file")},orderby="uid"):
      c+=1
#      print c," uid:",i.uid," kind:",i.kind," loc:",i.file_folder()," name:",i.name
      subfolder=i.file_folder()
      destfolder=dest+subfolder
      if not os.path.exists(destfolder):
        os.makedirs(destfolder)
      shutil.copy2(source+subfolder+"/"+i.code,destfolder)
      print("added %s" % (dest+subfolder+"/"+i.code,))
    return "clone completed: %s files added" % c

  @classmethod
  def pare_data(self,req):
    """prunes all obsolete data from the data/music folder
       Optional request parameter: ?source=<your data folder>
       1) moves all data to an "xmusic" destination folder
       2) then moves valid data back to source
       3) thus obsolete data remains in the "xmusic" folder, for manual deletion
    Assumes a proper filesystem (ie not exfat!)
    """
    # data folder
    source=req.source or "/home/howie/data/music/"
#    source=req.source or "/media/howie/backup/howie/data/music/"
##    source=req.source or "/media/howie/archive/data/music/" # DO NOT TRY ON EXFAT!!!!
    # rename the source folder, and create dest folder (as the original source)
    print('moving "music" folder to "xmusic"')
    dest=copy(source)
    source=source.replace("/music/","/xmusic/") # DODGY - will break if /music/ is duplicated in the path..
    os.rename(dest,source)
    # move the valid files to the original folder
    print("moving back the valid files...")
    c=0
    for i in self.list(isin={'kind':('file','image','track')},orderby="uid"):
      c+=1
      fn="%s/%s" % (i.file_folder(),i.code)
      print("keeping ",fn)
      os.renames(source+fn,dest+fn)
    print("done: ",c, " files retained")
    return "pare completed: %s files retained" % c

#  def move_plays(self,dt):
#      "copy plays for self to req.to, where req.to is a uid"
#      execute("update %s.plays set page=%s where page=%s " % (self.Config.database,req.to,self.uid))
#      return "plays moved"


  def move_plays(self,req):
    "move plays from self to req.to - for tracks only - does not update scores"
    if self.kind=="track":
      if req.to:
        tob=self.get(req.to)
        if tob and tob.kind=="track":
          execute("update %s.plays set page=%s where page=%s " % (self.Config.database,tob.uid,self.uid))
          req.message="plays moved to track %s" % tob.uid
        else:
          req.warning="nothing done as valid '?to=' track-uid is required" 
      else:
        req.warning="nothing done - '?to=' track-uid is required"
    else:
      req.warning="nothing done as this is not a track"
    return self.view(req)

  #  for use when replacing tracks and albums with better versions
  def move_info(self,req):
    """copies self data to req.to, for tracks and albums, and disables self
    EXPECTS req.to
    self must be an album or track
    - for tracks, COPIES track data
    - for albums, COPIES album data and all track data
    MOVES all track and album images
  
    BEWARE - relies on album track numbers being correct and fully corresponding

    NOTE: will have to run fix_scores() after copying all required album/track info
          =========================================================================
    """
    def copy_item(st,dt):
        "copy info from st to dt"
        # move plays
#        print "moving plays for ",st.uid," to ",dt.uid
        execute("update %s.plays set page=%s where page=%s " % (self.Config.database,dt.uid,st.uid))
        # move tags 
        execute("update %s.tags set page=%s where page=%s " % (self.Config.database,dt.uid,st.uid))
        # copy info
        dt.name=st.name
        dt.when=st.when
        dt.composer=st.composer
        dt.artist=st.artist
        dt.text=st.text
        dt.rating=st.rating
        dt.prefs=st.prefs
        #dt.score=st.score
        dt.flush()
        st.name=st.name+" (old version)"
        st.rating= -4 #  set to X 
        st.flush()
        # move images
        st.get_images() # create st.images
        for i in  st.images:
          i.parent=dt.uid
          i.set_lineage(pob=dt)
          i.flush()
    try:
      dob=self.get(safeint(req.to))
    except:
      dob=None
    if (not dob):
      return "specify destination as ?to=[UID]"
    elif (self.kind!=dob.kind):
      return "source is a %s but destination is a %s" % (self.kind,dob.kind)  
    if self.parent!=dob.parent:
      return "source and destination parent mismatch"
    if self.kind=='album':
      copy_item(self,dob)
#      for st in self.list(parent=self.uid,kind='track',where="rating>=0",orderby="uid"):
      for st in self.list(parent=self.uid,kind='track',orderby="uid"):
        dt=dob.list(parent=dob.uid,kind="track",seq=st.seq) # get corresponding track from dob
        if dt:
          copy_item(st,dt[0])
    elif self.kind=='track':
      copy_item(self,dob)
    else:
      return "not an album or track..."
    req.message="info copied/moved to %s" % dob.uid
    return self.view(req)
      

######## ad hoc and tests #################################

  @classmethod
  def test(self,req):
    ""
    m=self.transport.get_media()
    pos=self.player.list.index_of_item(m)
    print("pos= %s" % pos)
    return "pos= %s" % pos


  def reset_length(self,req):
    ""
    self.set_length()
    return self.view(req)

  def tidy_tags(self,req):
    "removes any obsolete tags - THERE SHOULD NOT BE ANY!"
    count=0
    for t in self.Tag.list():
      if not self.exists(t.page):
        t.delete()
        count+=1
    return "%s obsolete tags deleted" % count    

  def fix_tags(self,req):
    "ad hoc..."
#    n=0
#    for t in self.list(where="uid>9772",kind='track'):
#      t.add_tag('Chillout')
#      n=n+1 
#    return "%s tags added" % n  
   

  def fix_ratings(self,req):
    "ONE_OFF UTILITY"
    for i in self.list(kind='track'):
      if (i.rating==-1) and (not i.parent in (5232,1536,1795,1877)): 
        i.rating=0
        i.flush()
    req.message='ratings fixed'      
    return self.view(req)     


  @classmethod
  def fix_lengths(self,req):
    "utility to fix all track and album lengths"
    c=0
    for t in self.list(kind='track'):
      if not t.length: # for speed, assume if we have a length that it is correct (as audio files are never altered here)
        t.set_length()
        c+=1
    for aob in self.list(kind='album'):
      aob.set_length()
    return "%s track lengths added - all album lengths updated" % c

  @classmethod
  def fix_summary_scores(cls,req):
    ""
    for i in cls.list(isin={"kind":['artist','album']}):
      i.update_score()
    return "artist and album score totals updated"

  def fix_score(self,req):
    """ re-calculate plays (i.e. score) 
      - for one track from the plays table
      - or for one album or artist from the child scores
      self must be a track, artist, or album
    """
    if self.kind in ("album","artist"):
      self.update_score()
      req.message="score reset from child scores"
    elif self.kind=="track":
      self.score=0
      for i in self.Play.list(page=self.uid):
        self.score+=i.times
      self.flush()
      req.message="score reset from plays table"
    else:
      req.error= "not a track, album, or artist"
    return self.view(req)

  @classmethod
  def fix_scores(cls,req):
    """ crudely but simply re-calculates plays (i.e. score) 
       - gets play totals for every track record from plays table
       - then re-calculates all album and artist summary scores
    """
#    if from_uid==1:     
    print("resetting scores to zero...")
    cls.list(asObjects=False,sql="update `%s`.pages set score=0" % cls.Config.database)
    print("adding play scores ...")
#    for i in cls.Play.list(where= ("uid>=%s" % req.from_uid) if (req.from_uid>1) else ""):
    for i in cls.Play.list():
      try: 
        tob=cls.get(i.page)
        tob.score=tob.score+i.times
        tob.flush()
#      except Exception as e:
#        print "ERROR with ",i.page,' : ',e
      except:
        print("deleting %s play(s) for missing track %s" % (i.times,i.page))
        i.delete() # delete invalid plays (presumably the track is already deleted)
    print("calculating summary scores")
    cls.fix_summary_scores(req)
    print("done")
    return "all scores reset from plays table"

  def extract_version(self):
    "one-off script to extract version information from and album or track and put it in version field"
    if self.kind not in ['album','track']:
      return False
    lines=self.text.split('\n')
    text=[]
    self.version=""
    for l in lines:
      if (not self.version) and (l.lstrip()[0:2]=='* '): #likely version info
        self.version=l.strip()[2:]
        print('got version for ', self.kind, self.uid, ' : ', self.version)
      else:
        text.append(l)
    if self.version:
      self.text='\n'.join(text)
      self.flush()
    return True

#  def get_pics(self,req):
#    '''
#     sensible defaults eg 500x500 for albums, 300x300 for tracks
#    '''
#    req.error="DISABLED"
#    return self.view(req)
#
#    root=self.get(3)
#    count=0
#    for artist in root.get_children():
###     if artist.uid>7926:
##    artist=self.get(4)
#      for album in artist.get_children():
#       if not album.name: # second pass to get untitled track pics
#        for t in album.get_children():
#          print "====== checking %s",t.uid, t.name
#          data=t.get_track_data()  
#          path= data.get('arturl','') and data['arturl'].startswith("file") and urllib.url2pathname(data['arturl'])[7:] or ""
#          if path:
#            if t.pic_saved(path):
##            if album.pic_saved(req,path,size='500'):
#              count+=1
#              break 
#    req.message="%s pics added" % count          
#    return self.view(req)  

#  def set_album_artists(self,req):
#    ""
#    for i in self.list(kind='album'):
#      i.artist=i.get_pob().name
#      i.flush()
#    return self.view(req)

#  def create_genre_playlists(self,req):
#    "ONE OFF UTILITY to generate genre playlists - call from genres page"
#    for genre in self.get_tagnames():
#          # create playlist
#          r=Req()
#          r.name=genre
#          r.kind='smartlist'
#          r.stage='posted'
#          r.rating=1 
#          ob=self.create_page(r) 
#          ob.add_tag(genre)
#          ob.flush
#    return self.view(req)      

#  def rate_children(self,req):
#    "for playlists and genres kinds only"
#    if self.kind in ('playlists','genres'):
#      for i in self.get_children():
#        i.rating=1
#        i.flush()
#    return self.view(req)      


 # def derive_album_tags(self):
 #   "ONE-OFF UTILITY for use with derive_all_album_tags() -  get an album's tags from its track tags"
 #   tags=self.get_tags() # get existing album tags
 #   # get track tags
 #   tracks=[i.uid for i in self.get_children_by_kind(kind='track')]
 #   print 'uid=',self.uid,' tracks= ',tracks
 #   if tracks:
 #     tracktags=[i['name'] for i in self.Tag.list(asObjects=False,isin={'page':tracks},what='distinct name')]
 #     print 'uid=',self.uid,' tracktags= ',tracktags
 #     # add any new ones
 #     for t in tracktags:
 #       if not t in tags:
 #         self.add_tag(t)
 #         print 'tag %s added' % t
 #     return True
 #   return False    
           
#  def derive_all_album_tags(self,req):
#    "ONE-OFF UTILITY derive tags for every album" 
#    count=0
#    for album in self.list(kind='album'):
#      if album.derive_album_tags():
#        count+=1
#    req.message="tags derived from tracks for %s albums" % count  
#    return self.view(req)    


# The following has been disabled as player.is_shuffling is no longer in use.
# It works and can be reused for other variables if/when required
#
## SAVE AND RESTORE STATE AT-EXIT #################################
##
## can't use Var() because it is not accessible yet (during module load), so just use a file "state"
#
#def save_state():
#    ""
#    f=open("state",'w')
#    f.write("is_shuffling=%s" % (Page().player.is_shuffling and 1 or 0))
#    f.close()
#    
#def restore_state():
#    ""
#    try:
#      f=open("state",'r')
#      name,val=f.readline().split('=')
#      Page().player.is_shuffling=bool(safeint(val))
#      f.close()
#    except:
#      raise
#      pass
# 
#import atexit
#restore_state()
#atexit.register(save_state)
