function JukeboxViewModel() {
    this.user = new UserViewModel();
    this.player = new PlayerViewModel(this.user);
    this.queue = new QueueViewModel(this.user);
    this.search = new SearchViewModel(this.user);
    this.version = new VersionViewModel();
    this.roots = new RootsViewModel();
}
JukeboxViewModel.prototype.setup = function() {
    ko.applyBindings(this);
    this.player.setup();
    this.user.setup();
    this.queue.setup();
    this.search.setup();
    this.version.setup();
    this.roots.setup();
}
JukeboxViewModel.prototype.update = function(status) {
    this.player.update(status);
    this.queue.update(status.queue, status.queueInfo);
}

function updateJukebox(status) {
    jukebox.update(status);
}
