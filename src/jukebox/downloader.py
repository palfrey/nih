from utils import urlopen, URLError, BackgroundTask, registerStartupTask
from os.path import join
from models import *
from simple_player import Status

class Downloader(BackgroundTask):
    def processItem(self,item):
        hash = item.hash()
        from cache import cacheFolder, cached
        cacheFile = join(cacheFolder, hash)
        try:
            data = urlopen(item.url).read()
            open(cacheFile, "wb").write(data)
            cached(item)
        except URLError:
            item.failed = True
            item.save()

    def postProcessItem(self, item):
        from jsonfuncs import next_track, play_current, get_status
        current = QueueItem.current().what
        if item.failed:
            print "item failed", item
            char = ChatItem(what="failed", info = item)
            char.save()
            if current == item:
                next_track()
        elif current == item and get_status() == Status.idle:
            play_current()
    
    def downloads(self):
        with self.queueCondition:
            ret = list(self.queue)
            return ret

downloader = registerStartupTask(Downloader)

