function QueueItem(item, info, queue) {
    this.queue = queue;

    this.id  = ko.observable(item.id);
    this.who = ko.observable(item.username);
    this.url = ko.observable(item.url);

    this.trackName   = ko.observable();
    this.trackNumber = ko.observable();
    this.albumTitle  = ko.observable();
    this.artistName  = ko.observable();
    this.totalTime   = ko.observable();

    if (info && info.trackName) {
        this.trackName(info.trackName);
        this.trackNumber(info.trackNumber);
        this.albumTitle(info.albumTitle);
        this.artistName(info.artistName);
        this.totalTime(info.totalTime);
    } else {
        this.trackName(this.short_url(this.url()));
    }
}
QueueItem.prototype.short_url = function(url) {
    var part = url.substr(url.lastIndexOf('/') + 1);
    part = unescape(part);
    return part.replace(/_/g, ' ');
}

function QueueViewModel(user) {
    this.user = user;
    this.items = ko.observableArray();
    this.busy = false;

    this.count = ko.computed(function() {
        return this.items().length;
    }, this);
}
QueueViewModel.prototype.remove = function(item) {
    rpc("dequeue", [this.user.name(), item.id()], updateJukebox);
    this.items.remove(item);
}
QueueViewModel.prototype.update = function(items, infos) {
    if (!this.busy) {
        this.items.removeAll();
        for (var i = 0; i < items.length; i++) {
            this.items.push(new QueueItem(items[i], infos[i], this));
        }
    }
}
QueueViewModel.prototype.setup = function() {
    var me = this;
    $("#queue").on("click", "li.item .remove", function() {
        var item = ko.dataFor(this);
        item.queue.remove(item);
    });
    $("#queue ol").sortable({
        revert: true,
        axis: "y",
        start: function(event, ui) {
            me.busy = true;
        },
        stop: function(event, ui) { 
            var item = ko.dataFor(ui.item.get(0));
            // Server indexes from 1, jquery UI from 0
            rpc("reorder", [item.id(), ui.item.index() + 1]);
            me.busy = false;
        },
    });
}
