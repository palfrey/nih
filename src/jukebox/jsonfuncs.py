from jsonrpc import jsonrpc_method
from jsonrpc.site import JSONRPCSite
from models import *
from time import mktime, strftime, gmtime
from urllib import unquote
from random import sample
from alsaaudio import Mixer, ALSAAudioError
from cache import cached, albumArt
from threading import Thread
from simple_player import Player, Status
import gobject
from utils import registerStartupTask
from os.path import join
import audioscrobbler
from django.conf import settings
from downloader import downloader
from socket import gethostbyaddr

def make_audioscrobbler():
    if settings.LASTFM_ENABLED:
        audioscrobbler.enc = "utf8"
        return audioscrobbler.AudioScrobblerPost(username=settings.LASTFM_USER, password=settings.LASTFM_PASSWORD, verbose=True)
    else:
        def do_nothing(**kwargs):
            pass
        return do_nothing

site = JSONRPCSite()
post = make_audioscrobbler()

@jsonrpc_method('get_username', site=site)
def get_username(request):
    return request.session.get('username', None)         \
        or str(request.META.get("REMOTE_HOST", ""))      \
        or gethostbyaddr(request.META["REMOTE_ADDR"])[0] \
        or "Unknown"

@jsonrpc_method('set_username', site=site)
def set_username(request, username):
    request.session['username'] = username
    return username

def metadata(item):
    if not item.got_metadata:
        return None
    ret = { 
        "artistName": item.artist, 
        "albumTitle": item.album, 
        "trackName": item.title, 
        "trackNumber":item.trackNumber, 
        "totalTime": item.trackLength
    }
    if albumArt(item):
        ret["cacheHash"] = item.hash()
    return ret

def status_info(request):
    objects = QueueItem.objects.all()
    items = [{
        "id": x.id, 
        "url": x.what.url, 
        "username": x.who, 
        "index": x.index } for x in objects]
    itemsMeta = [metadata(x.what) for x in objects]
    if len(items)>0:
        first = (items[0], itemsMeta[0])
    else:
        first = (None, None)

    elapsed = player.elapsed()
    current = QueueItem.current()
    if current!=None and current.what in downloader.downloads():
        state = "caching"
    else:
        state = player.status.name()

    return {
        "status":state,
        "entry":first[0],
        "info": first[1],
        "queue": items[1:],
        "queueInfo": itemsMeta[1:],
        "paused": player.status != Status.playing,
        "elapsedTime": elapsed,
        "downloads": [x.url for x in downloader.downloads()]
    }

@jsonrpc_method('search', site=site)
def search(request, inp):
    items = MusicFile.objects
    for term in inp:
        items = items.filter(url__icontains=term)
    items = items.order_by('parent__url', 'url')
    return [{"url": x.url, "info": metadata(x)} for x in items]

@jsonrpc_method('randomtracks', site=site)
def randomtracks(request, count):
    items = MusicFile.objects.all()
    count = min(count, items.count())
    ret = [{"url":items[x].url} for x in sample(range(items.count()),count)]
    return ret

@jsonrpc_method('enqueue', site=site)
def enqueue(request, username, tracks, atTop):
    for t in tracks:
        q = QueueItem(who = username, what = MusicFile.objects.get(url=t['url']))
        cached(q.what)
        try:
            if atTop:
                items = QueueItem.objects.all().order_by("index")
                if len(items)> 1:
                    q.index = (items[0].index+items[1].index)/2
                else:
                    q.index = items[0].index + 1 # only current item in queue
            else:
                q.index = QueueItem.objects.order_by("-index")[0].index + 1 # only current item in queue
        except IndexError: # nothing else in queue
            q.index = 0
        q.save()
    return status_info(request)

@jsonrpc_method('dequeue', site=site)
def dequeue(request, username, trackId):
    queue = list(QueueItem.objects.all())[1:]
    for item in queue:
        if item.id == trackId:
            item.delete()
    reindex_queue()
    return status_info(request)

@jsonrpc_method('clear_queue', site=site)
def clear_queue(request, username):
    queue = list(QueueItem.objects.all())[1:]
    for item in queue:
        item.delete()
    return status_info(request)

@jsonrpc_method('get_queue', site=site)
def get_queue(request):
    return status_info(request)

@jsonrpc_method('reorder', site=site)
def reorder(request, trackId, new_position):
    queue = list(QueueItem.objects.all())[1:]
    length = len(queue)
    if new_position < 1:
        raise Exception("Cannot move items above position 1 in the queue")
    if new_position > length:
        new_position = length
    
    mover = QueueItem.objects.get(id=trackId)
    old_position = mover.index
    if old_position == 0:
        raise Exception("Cannot move the currently playing track")

    # Shuffle items that were previously below this item up to fill
    # the gap it left when it moved down
    if new_position > old_position: 
        for _, item in enumerate(queue):
            if item.index > old_position and item.index <= new_position:
                item.index -= 1
                item.save()

    # Shuffle items that were previously above this item down to fill
    # the gap it left when it moved up
    if new_position < old_position: 
        for _, item in enumerate(queue):
            if item.index >= new_position and item.index < old_position:
                item.index += 1
                item.save()

    mover.index = new_position
    mover.save()

    return status_info(request)

volume_who = ""
volume_direction = ""

def volume():
    try:
        volume = Mixer().getvolume()[0]
    except ALSAAudioError:
        volume = 'Error'
    return {"volume":volume, "who":volume_who, "direction": volume_direction}

@jsonrpc_method('get_volume', site=site)
def get_volume(request):
    return volume()

@jsonrpc_method('set_volume', site=site)
def set_volume(request, username, value):
    global volume_who, volume_direction
    m = Mixer()
    if value > m.getvolume()[0]:
        volume_direction = "up"
        volume_who = username
    elif value < m.getvolume()[0]:
        volume_direction = "down"
    else:
        return volume() # no change, quit
    
    volume_who = username
    m.setvolume(value)
    return volume()


def chat_history(request, limit):
    ret = []
    for item in ChatItem.objects.all()[:limit]:
        msg = { 
            "when": mktime(item.when.timetuple()),
            "what": item.what
        }
        if item.who:
            msg["who"] = item.who

        player_actions = [
            'skip',
            'play',
            'pause',
            'resume',
        ]

        if item.what in player_actions:
            msg["track"] = {"url":item.info.url}
            msg["info"] = metadata(item.info)
        elif item.what == "failed":
            msg["error"] = "Failed to download %s"%item.info.url
        else:
            msg["message"] = item.message
        ret.append(msg)
    return ret

@jsonrpc_method('chat', site=site)
def chat(request, username, text):
    ChatItem(what="says", message=text, who=username).save()

@jsonrpc_method('get_history', site=site)
def get_history(request, limit):
    return chat_history(request, limit)

def reindex_queue():
    index = 0
    for _, item in enumerate(QueueItem.objects.all()):
        item.index = index            
        item.save()
        index += 1

def next_track():
    if QueueItem.objects.all().count() > 0:
        QueueItem.current().delete() # remove current first item from queue
        player.stop()
        reindex_queue()
    if QueueItem.objects.all().count()>0:
        play_current()
    elif player.status != Status.idle:
        player.stop()

player = Player()
player.next_track = next_track

@jsonrpc_method('skip', site=site)
def skip(request, username):
    current = QueueItem.current()
    if current != None:
        ChatItem(what="skip", info = current.what, who=username).save()
        print "saved item"
        next_track()
    return status_info(request)

class Looper(Thread):
    def run(self):
        loop = gobject.MainLoop()
        loop.run()

gobject.threads_init()
registerStartupTask(Looper)

def play_current():
    toplay = QueueItem.current()
    f = cached(toplay.what)
    print "toplay", f
    if f != None:
        player.play(f)
        song = toplay.what
        track = dict(artist_name=song.artist,
                 song_title=song.title,
                 length=int(song.trackLength),
                 date_played=strftime("%Y-%m-%d %H:%M:%S", gmtime()), 
                 album=song.album,
                 mbid=""
                )
        print "track", track
        post(**track)
        ChatItem(what="play", info=song, who=toplay.who).save()
    else:
        player.stop()
        ChatItem(what="stop", who=None).save()

@jsonrpc_method('pause', site=site)
def pause(request, shouldPause, username):
    current = QueueItem.current()
    if not shouldPause:
        if player.status == Status.idle and QueueItem.objects.count()>0:
            from cache import is_cached
            if is_cached(current.what):
                play_current()
        elif player.status == Status.paused:
            player.unpause()
            ChatItem(what="resume", info=current.what, who=username).save()
    else:
        if player.status == Status.playing:
            player.pause()
            ChatItem(what="pause", info=current.what, who=username).save()

    return status_info(request)

@jsonrpc_method('get_version', site=site)
def get_version(request):
    import version
    return version.get_version()

def get_status():
    return player.status

