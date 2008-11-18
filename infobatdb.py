#!/usr/bin/twistd -y
from __future__ import with_statement
import re, bsddb3, random, collections, threading, urllib, struct
from datetime import datetime
from twisted.web import xmlrpc
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, task
from twisted.protocols import policies
from twisted.application import internet, service
ORDER = 4
_words_regex = re.compile(r"(^\*)?[a-zA-Z',.!?\-:; ]")
_paste_regex = re.compile(r"URL: (http://[a-zA-Z0-9/_.-]+)")
start = datetime.now()

import ConfigParser
conf = ConfigParser.ConfigParser(dict(port='6667', channels='#infobat'))
conf.read(['infobat.cfg'])

_chain_struct = struct.Struct('>128H')
class Chain(object):
    def __init__(self, data=None):
        if self.data is None:
            self.data = [0] * 128
        else:
            self.data = list(_chain_struct.unpack(data))
    
    def __setitem__(self, key, value):
        self.data[ord(key)] = value
    def __getitem__(self, key):
        return self.data[ord(key)]
    def __delitem__(self, key):
        self.data[ord(key)] = 0
    
    def pack(self):
        return _chain_struct.pack(*self.data)
    
    def choice(self):
        which = random.randrange(sum(self.data))
        partial_sum = 0
        for index, val in enumerate(self.data):
            if val + partial_sum > which:
                return chr(index)
            partial_sum += val
    
    def append(self, key):
        self.data[ord(key)] += 1
    
    def merge(self, data=None, chainobj=None):
        if chainobj is None:
            chainobj = Chain(data)
        self.data = [v1 + v2 for v1, v2 in zip(self.data, chainobj.data)]

_redent_pattern = re.compile('([^:;]*)([:;]|$)')
_valid_first_words = set(
    'if elif else for while try except finally class def with'.split())
def redent(s):
    ret, indent = [['']], 0
    for tok in _redent_pattern.finditer(s):
        line, end = [st.strip() for st in tok.groups()]
        first_word = line.partition(' ')[0]
        if line:
            if end == ':':
                line += ':'
            ret[-1].append(line)
            if end == ':' and first_word in _valid_first_words:
                indent += 1
            if end != ':' or first_word in _valid_first_words:
                ret.append(['    ' * indent])
        else:
            indent -= 1
            ret[-1][0] = '    ' * indent
    return '\n'.join(''.join(line) for line in ret)

def gen_shuffle(iter_obj):
    sample = range(len(iter_obj))
    while sample:
        n = sample.pop(random.randrange(len(sample)))
        yield iter_obj[n]

svnURL = '$HeadURL$'.split()[1]
svnRevision = 'r' + '$Revision$'.split()[1]

class Infobat(irc.IRCClient):
    nickname = conf.get('irc', 'nickname')
    max_countdown = conf.getint('database', 'sync_time')
    wordcount = chaincount = 0
    identified = False
    db = None
    
    sourceURL = svnURL
    versionName = 'infobat'
    versionNum = svnRevision
    versionEnv = 'twisted'
    
    def _load_database(self):
        self.db = bsddb3.hashopen(conf.get('database', 'db_file'), 'cf')
        if '__offset__' not in self.db:
            self.db['__offset__'] = '0;0'
            self.db['__start__'] = ''
            self.db['__act__'] = ''
            self.db.sync()
        self.start_offset, self.actions = [
            int(x) for x in self.db['__offset__'].split(';')]
    
    def signedOn(self):
        nickserv_pw = conf.get('irc', 'nickserv_pw')
        if nickserv_pw:
            self.msg('NickServ', 'identify %s' % nickserv_pw)
        self._load_database()
        self.looper = task.LoopingCall(self._sync_countdown)
        self.countdown = self.max_countdown
        self._updates = collections.defaultdict(Chain)
        self._start_update = []
        self._act_update = []
        self.updates_lock = threading.Lock()
        self.looper.start(30)
    def _sync_countdown(self):
        if self.db is None: return
        self.countdown -= 1
        if self.countdown == 0:
            self._sync()
            self.countdown = self.max_countdown
    def _sync(self):
        for chain, chainobj in self._updates:
            dbchain = self.db.get(chain)
            if dbchain:
                chainobj.merge(dbchain)
            packed = chainobj.pack()
            self.db[chain] = packed
        self._updates.clear()
        if self._start_update:
            self.start_offset += len(self._start_update)
            self.db['__start__'] += ''.join(self._start_update)
            self._start_update = []
        if self._act_update:
            self.actions += len(self._act_update)
            self.db['__act__'] += ''.join(self._act_update)
            self._act_update = []
        self.db['__offset__'] = '%d;%d' % (self.start_offset, self.actions)
        self.db.sync()
    def append_chain(self, chain, val):
        self._updates[chain].append(val)
        self.countdown = self.max_countdown
    def learn(self, string, action=False):
        if self.db is None: return
        if string.startswith('*'):
            action = True
            string = string.lstrip('*')
        queue, length = '', 0
        for w in _words_regex.finditer(string):
            self.wordcount += 1
            w = w.group().lower()
            if not queue and w == ' ': continue
            if len(queue) == ORDER:
                self.append_chain(queue, w)
            if w[-1] in '.!?':
                queue, length, action = '', 0, False
            else:
                queue += w
                length += 1
                if length == ORDER:
                    if action:
                        self._act_update.append(queue)
                    else:
                        self._start_update.append(queue)
                queue = queue[-ORDER:]
    
    def kickedFrom(self, channel, kicker, message):
        self.join(channel)
    def action(self, user, channel, message):
        if not user: return
        if channel != self.nickname:
            self.learn(message, True)
    def privmsg(self, user, channel, message):
        if not user: return
        user = user.split('!', 1)[0]
        if (user.lower() == 'nickserv' and not self.identified and 
                'identified' in message):
            self.identified = True
            self.join(conf.get('irc', 'channels'))
        if user.lower() in ('nickserv', 'chanserv', 'memoserv'): return
        target = (user if channel == self.nickname else channel)
       
        if channel != self.nickname:
            self.learn(message)
        
        if 'porcupine tree' in message.lower():
            self.msg(target, "they're better live.")
            return
        m = re.match(
            r'^s*%s\s*[,:> ]+(\S?.*?)[.!?]?\s*$' % self.nickname, message, re.I)
        if m:
            command, = m.groups()
        elif channel == self.nickname:
            command = message
        else:
            return
        s_command = command.split(' ')
        command_func = getattr(self, 'infobat_' + s_command[0], None)
        if command_func is not None:
            command_func(target, *s_command[1:])
        elif self.db is not None and self.start_offset + self.actions > 0:
            choices = _words_regex.findall(command)
            start_choice = random.randrange(self.start_offset + self.actions)
            action = False
            if start_choice < self.start_offset:
                start_choice *= ORDER
                result = self.db['__start__'][start_choice:start_choice + ORDER]
            else:
                start_choice = (start_choice - self.start_offset) * ORDER
                result = self.db['__act__'][start_choice:start_choice + ORDER]
                action = True
            try:
                result += random.choice(self.db[result])
            except KeyError:
                pass
            else:
                self.chaincount += 1
                search = result[-ORDER:]
                while 1:
                    try:
                        chain = self.db[search]
                    except KeyError:
                        break
                    if random.randrange(ORDER) == 0:
                        chain_ = filter(lambda x: x not in '.!? ', chain)
                        if chain_:
                            chain = chain_
                    for next in gen_shuffle(choices):
                        if next in chain:
                            choices.remove(next)
                            break
                    else:
                        next = random.choice(chain)
                    if len(result) + len(next) > 255:
                        break
                    result += next
                    search = (search + next)[-ORDER:]
                    self.chaincount += 1
            if action:
                self.me(target, result)
            else:
                if channel != self.nickname:
                    result = user + ', ' + result
                self.msg(target, result)
    
    def infobat_redent(self, target, paste_target, *text):
        redented = redent(' '.join(text))
        proxy = xmlrpc.Proxy('http://paste.pocoo.org/xmlrpc/')
        d = proxy.callRemote('pastes.newPaste', 'python', redented)
        d.addCallbacks(self._redent_success, self._redent_failure,
            callbackArgs=(target, paste_target), errbackArgs=(target,))
    
    def _redent_success(self, id, target, paste_target):
        self.msg(target, '%s, http://paste.pocoo.org/show/%s/' % (
            paste_target, id))
    def _redent_failure(self, failure, target):
        self.msg(target, 'Error: %s' % failure.getErrorMessage())
        return failure
    
    def infobat_sync(self, target):
        if self.db is None: return
        self._sync()
        self.msg(target, 'Done.')
    def infobat_unlock(self, target):
        if self.db is not None:
            self.looper.stop()
            self.db.sync()
            self.db.close()
            self.db = None
            self.msg(target, 'Database unlocked.')
        else:
            self.msg(target, 'Database was unlocked.')
    def infobat_lock(self, target):
        if self.db is None:
            self._load_database()
            self.looper.start(30)
            self.msg(target, 'Database locked.')
        else:
            self.msg(target, 'Database was unlocked.')
    def infobat_stats(self, target):
        if self.db is None: return
        delta = datetime.now() - start
        timestr = []
        if delta.days:
            timestr.append('%d days' % delta.days)
        minutes, seconds = divmod(delta.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            timestr.append('%d hours' % hours)
        if minutes:
            timestr.append('%d minutes' % minutes)
        if seconds:
            timestr.append('%d seconds' % seconds)
        if not timestr:
            timestr = ''
        elif len(timestr) == 1:
            timestr = timestr[0]
        else:
            timestr = '%s and %s' % (', '.join(timestr[:-1]), timestr[-1])
        result = ("I have been online for %s. In that time, I've processed %d "
            "characters and spliced %d chains. Currently, I reference %d "
            "chains with %d beginnings (%d actions).") % (
                timestr, self.wordcount, self.chaincount, len(self.db) - 3,
                self.start_offset + self.actions, self.actions
            )
        self.msg(target, result)
    def infobat_divine(self, target, *seed):
        self.me(target, 'shakes the psychic black sphere.')
        r = random.Random(''.join(seed) + datetime.now().isoformat())
        st = open('magic8.txt')
        l = st.readlines()
        st.close()
        l = r.choice(l).strip()
        self.msg(target, 'It says: "%s"' % l)

class InfobatFactory(protocol.ReconnectingClientFactory):
    protocol = Infobat

ircFactory = InfobatFactory()
ircService = internet.TCPClient(
    conf.get('irc', 'server'), conf.getint('irc', 'port'), ircFactory, 20, None)

application = service.Application('infobat')
ircService.setServiceParent(application)
