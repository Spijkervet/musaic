
#pylint: disable=invalid-name,missing-docstring

from copy import deepcopy
from random import randint
from collections import defaultdict

from mido import MidiFile
from mido.frozen import FrozenMessage

DEFAULT_META_DATA = {
    'ts': '4/4',
    'span': 10.0,
    'jump': 1.5,
    'cDens': 0.25,
    'cDepth': 1.0,
    'tCent': 62.0,
    'rDens': 1.2,
    'pos': 0.0,
    'expression': 0
}

DEFAULT_SECTION_PARAMS = {
    'length': 4,
    'loop_num': 1,
    'octave': 4,
    'velocity_range': (80, 100),
    'note_length': 0,
    'transpose_octave': 0,
}

DEFAULT_AI_PARAMS = {
    'loop_alt_len': 0,
    'loop_alt_num': 2,
    'sample_mode': 'dist',
    'lead_mode': 'melody',
    'context_mode': 'inject',
    'lead': None,
    'injection_params': (('qb', 'eb'), 'maj'),
    'lead_bar': None,
    'prev_bars': None,
    'chord_mode': 0,
    'meta_data': None,
}

def forceListLength(l, length, alt=None):
    if len(l) > length:
        return l[:length]
    return l + [alt for _ in range(length - len(l))]


class Measure:
    '''
    Measure: Holds note values and associated times
    '''
    def __init__(self, id_, chan=1, notes=None, events=None,
                 transpose_octave=0, note_length=None):

        self.id_ = id_
        self.chan = chan
        self.transposeOctave = transpose_octave
        self.noteLength = note_length
        self.velocityRange = (80, 100)

        self.callbacks = set()

        if notes:
            # Note: (nn, start_tick, end_tick), where nn=0 is a pause
            self.notes = notes
            self.MidiEvents = self.convertNotesToMidiEvents(notes)
            self.empty = False
        elif events:
            # {tick: MIDI Event} where MIDI Event = ('/eventType', (chan, nn, vel))
            self.MidiEvents = events
            # FIXME self.convertMidiEventsToNotes()
            self.notes = []
            self.empty = False
        else:
            self.setEmpty()

        self.genRequestSent = False

    def call(self):
        ''' calls functions whenever notes are updated '''
        for func in self.callbacks:
            func()

    def addCallback(self, func):
        self.callbacks.add(func)

    def removeCallback(self, func):
        if func in self.callbacks:
            self.callbacks.remove(func)

    def convertNotesToMidiEvents(self, notes):
        ''' Returns dictionary {onTime: list of MIDI messages}. Messages do not contain time attribute.'''
        events = defaultdict(list)
        for n in notes:
            if n[0] > 0:
                vel = randint(*self.velocityRange)
                onMsg = FrozenMessage('note_on', channel=self.chan, note = n[0], velocity=vel)
                offMsg = FrozenMessage('note_off', channel=self.chan, note = n[0], velocity=vel)

                events[n[1]].append(onMsg)
                events[n[2]].append(offMsg)

        return dict(events)

    def convertMidiEventsToNotes(self, events):
        #TODO
        pass

    def isEmpty(self):
        return self.empty

    def setNotes(self, notes):
        self.notes = notes
        self.convertNotesToMidiEvents(self.notes)
        self.empty = False
        self.genRequestSent = False
        self.call()

    def getNotes(self):
        ''' Use this to access the actual played notes (includes transpose and length)'''
        notes = []
        for n in self.notes:
            if n[0] > 0:
                nn = n[0] + 12*self.transposeOctave
                startTick = n[1]
                if self.noteLength:
                    endTick = startTick + self.noteLength
                else:
                    endTick = n[2]
                notes.append((nn, startTick, endTick))
        return notes

    def getMidiEvents(self):
        ''' Applies note length and velocity changes '''
        return self.convertNotesToMidiEvents(self.getNotes())

    def setMidiEvents(self, events):
        self.events = events
        # TODO: self.convertMidiEventsToNotes()
        self.empty = False
        self.genRequestSent = False
        self.call()

    def setOctave(self, transpose_octave):
        self.transposeOctave = transpose_octave
        self.call()

    def setNoteLength(self, length):
        if length and length > 0:
            self.noteLength = length
        else:
            self.noteLength = None
        self.call()

    def setVelocities(self, velocities):
        self.velocityRange = velocities

    def setEmpty(self):
        self.notes = []
        self.MidiEvents = dict()
        self.empty = True
        self.call()

    def getData(self):
        data = {
            'id': self.id_,
            'empty': self.empty,
            'notes': self.notes
        }

        return data

    def __getstate__(self):
        # in order to be picklable, must drop the callbacks...
        state = self.__dict__.copy()
        del state['callbacks']
        return state


class Track:
    '''
    Track: an ordered list of Blocks
    '''
    def __init__(self, instrument):
        ''' callback: function to call whenever self.track changes '''
        self.instrument = instrument

        # {bar number: block}
        self.track = dict()
        # {blockID: [start times]}
        self.blocks = defaultdict(list)

        self.flatMeasures = []
        self.callbacks = set()

    def call(self):
        ''' execute functions when self.track if updated '''
        for func in self.callbacks:
            func(self.track)

    def addCallback(self, func):
        self.callbacks.add(func)

    def removeCallback(self, func):
        if func in self.callbacks:
            self.callbacks.remove(func)

    def setTrack(self, new_track):
        self.track = new_track
        self.flattenMeasures()

    def appendSection(self, section):
        bar_num = len(self)
        return self.insertSection(bar_num, section)

    def insertSection(self, bar_num, section):
        #print(self.track, bar_num, section)
        if bar_num in self.track:
            # TODO: make smarter
            print('[Track]', idx, 'occupied, appending section to end')
            bar_num = len(self)
            #self.insertSection(len(self), section)
            #return

        section.addCallback(self.flattenMeasures)

        id_ = self.getNextBlockID()
        block = Block(id_, [section])

        self.track[bar_num] = block
        self.blocks[id_] = bar_num
        self.flattenMeasures()

        return bar_num

    def deleteBlock(self, id_):
        print('[Track]', 'deleteBlock', id_)
        start_time = self.blocks[id_]
        del self.track[start_time]
        del self.blocks[id_]
        self.flattenMeasures()
        print(self.flatMeasures)
        print(self.track)

    def getNextBlockID(self):
        x = 0
        for blockID in self.blocks.keys():
            x = max(x, blockID)
        return x+1

    def moveBlockFromTo(self, from_, to_):
        try:
            block = self.track[from_]
        except KeyError:
            print('[Track]', 'block at', from_, 'not found')
            return

        del self.track[from_]

        for section in block:
            self.insertSection(to_, section)

    def moveBlockTo(self, blockID, to_):
        start = self.blocks[blockID][0]
        self.moveSectionFromTo(start, to_)

    def flattenMeasures(self):
        ''' Recalculates all the start times '''
        #print('[Track]', 'flatten measures')

        new_blocks = defaultdict(list)
        new_track = dict()
        x = 0

        #print(self.track.items())
        for st in sorted(self.track.keys()):
            block = self.track[st]
            start_time = max(x, st)
            new_track[start_time] = block
            new_blocks[block.id_] = start_time
            x = start_time + len(block)
            #print('Section', section.name, 'starts at', start_time)

        self.track = new_track
        self.blocks = new_blocks
        self.flatMeasures = [None]*x

        for start_time, block in self.track.items():
            for i, m in enumerate(block.flattenMeasures()):
                self.flatMeasures[start_time+i] = m

        #print(self.flatMeasures)

        self.call()

    def measuresAt(self, n):
        ''' Returns None bars for n < 0 and n > length'''
        if isinstance(n, int):
            if n < 0 or n >= len(self):
                return None
            return self.flatMeasures[n]
        return [self.measuresAt(b) for b in n]

    def getBlocks(self):
        return [(bar_num, self.track[bar_num]) for bar_num in sorted(self.track.keys())]

    def getNumberOfBlocks(self):
        return len(self.track.keys())

    def getSectionTimes(self, id_):
        ''' Returns the bar number of the first occurance of section ID '''

        for st in sorted(self.track.keys()):
            block = self.track[st]
            if block.sections[0].id_ == id_:
                return st
        return None

    def getLastSection(self):
        try:
            bar_num = max(self.track.keys())
            return self.track[bar_num].sections[-1]
        except (ValueError, KeyError, IndexError):
            return None

    def getData(self):
        data = {
            'blocks': self.blocks,
            'track': dict()
        }

        data['blocks'] = dict(self.blocks)

        for barNum, block in self.track.items():
            data['track'][barNum] = block.getData()

        return data

    def setData(self, trackData):
        self.track = dict()
        self.blocks = defaultdict(list)

        for bID, v in trackData['blocks'].items():
            self.blocks[bID] = v

        for barNum, blockData in trackData['track'].items():
            sections = [self.instrument.sections[sID] for sID in blockData['sections']]
            for s in sections:
                s.addCallback(self.flattenMeasures)
            block = Block(int(blockData['id']), sections)
            self.track[int(barNum)] = block

        self.flattenMeasures()

    def __len__(self):
        return len(self.flatMeasures)

    def __repr__(self):
        s = ['_' for _ in range(len(self))]
        for st, sec in self.track.items():
            for i in range(len(sec)):
                s[st+i] = sec.name[0]

        return ''.join(s)


class SectionBase:
    '''
    Abstract base class for musical section.
    '''
    def __init__(self, name, id_, **kwargs):
        self.name = name
        self.id_ = id_

        # Section type: {'fixed', 'ai'}
        self.type_ = None

        self.callbacks = set()

        self.measures = dict()
        self.mainMeasures = []
        self.flatMeasures = []
        self.measureCount = 0

        self.params = {**DEFAULT_SECTION_PARAMS, **kwargs}
        #self.params = dict()
        #self.changeParameter(**{**DEFAULT_SECTION_PARAMS, **kwargs})
        self.changeParameter(**self.params)
        #for k, v in kwargs.items():
        #    self.params[k] = v


        self.flattenMeasures()

    def call(self):
        '''Call callback functions when parameters change'''
        for func in self.callbacks:
            func()

    def addCallback(self, func):
        self.callbacks.add(func)

    def removeCallback(self, func):
        if func in self.callbacks:
            self.callbacks.remove(func)

    def changeParameter(self, **kwargs):
        '''Change section parameters.'''
        print('[SectionBase]', 'change parameters:')
        for k, v in kwargs.items():
            print('  ', k, ':', v)
            self.params[k] = v

        self.flattenMeasures()

        if 'transpose_octave' in kwargs:
            #print('[Section]', 'updated section octave', kwargs['transpose_octave'])
            for m in self.measures.values():
                m.setOctave(kwargs['transpose_octave'])

        if 'note_length' in kwargs:
            #print('[Section]', 'updated note length', kwargs['note_length'])
            for m in self.measures.values():
                m.setNoteLength(kwargs['note_length'])

        if 'velocity_range' in kwargs:
            for m in self.measures.values():
                m.setVelocities(kwargs['velocity_range'])


    def measureAt(self, n):
        assert n < len(self.flatMeasures), f'Index {n} for Section {self.name} too large'

        if self.flatMeasures > 0:
            return self.flatMeasures[n]

        return None


    def flattenMeasures(self):
        length = self.params['length']
        track = [None] * (length*self.params['loop_num'])

        for i in range(self.params['loop_num']):
            track[i*length:i*length] = self.mainMeasures

        self.flatMeasures = track
        self.call()

    def mainLength(self):
        '''Length of section (excluding repeats)'''
        return self.params['length']


    def getData(self):
        '''Returns a dictionary of section data, for saving as JSON.'''
        data = {
            'name': self.name,
            'id': self.id_,
            'type': self.type_,
            'params': self.params,
            'main_measures': [],
            'measures': dict(),
        }

        for m in self.mainMeasures:
            if m:
                data['main_measures'].append(m.id_)
            else:
                data['main_measures'].append(None)

        for mID, measure in self.measures.items():
            data['measures'][mID] = measure.getData()

        return data

    def setData(self, secData):
        self.name = secData['name']
        self.id_ = secData['id']
        self.params = secData['params']
        self.mainMeasures = []
        self.measures = dict()

        for mID, mData in secData['measures'].items():
            measure = Measure(mData['id'], notes=mData['notes'])
            measure.addCallback(self.flattenMeasures)
            self.measures[int(mID)] = measure

        for mID in secData['main_measures']:
            if mID == None:
                self.mainMeasures.append(None)
            else:
                self.mainMeasures.append(self.measures[int(mID)])

        if len(self.measures.keys()) > 0:
            self.measureCount = max(self.measures.keys()) + 1
        else:
            self.measureCount = 0

        self.flattenMeasures()

    def __len__(self):
        return self.params['length'] * self.params['loop_num']

    def __repr__(self):
        return f'|{self.name}, {self.params["length"]}'

    def __str__(self):
        return '|' + ''.join(map(str, self.flatMeasures))




#class Section:
#    '''
#    Section: collection of parameters, attributes and properties of a musical section.
#    '''
#    def __init__(self, name, id_, blank=False, **kwargs):
#        self.name = name
#        self.id_ = id_
#
#        self.callbacks = set()
#
#        self.params = deepcopy(DEFAULT_SECTION_PARAMS)
#        for k, v in kwargs.items():
#            self.params[k] = v
#
#        #self.blank = blank
#
#        self.mainMeasures = []
#        self.altEnds = [[]]
#        self.flatMeasures = [None]*self.params['length']
#        self.measures = dict()
#        self.measureCount = 0
#
#        self.changeParameter(**self.params)
#
#    def call(self):
#        ''' call functions when parameters change'''
#        for func in self.callbacks:
#            func()
#
#    def addCallback(self, func):
#        self.callbacks.add(func)
#
#    def removeCallback(self, func):
#        if func in self.callbacks:
#            self.callbacks.remove(func)
#
#    def newMeasure(self, notes=None, events=None):
#        id_ = self.measureCount
#        if 'chan' in self.params:
#            m = Measure(id_, chan=self.params['chan'], notes=notes, events=events)
#        else:
#            m = Measure(id_, notes=notes, events=events)
#
#        m.addCallback(self.flattenMeasures)
#        self.measures[id_] = m
#        self.measureCount += 1
#        return m
#
#    def changeParameter(self, **kwargs):
#        #print('[Section]', 'changeParameter', kwargs)
#        for key, val in kwargs.items():
#            self.params[key] = val
#            if key == 'lead' and val == -1:
#                self.params['lead'] = None
#
#        # make sure looping lengths are all correct
#        if self.params['loop_alt_len'] >= self.params['length']:
#            self.params['loop_alt_len'] = self.params['length'] - 1
#
#        # fill in extra measures
#        for _ in range(max(0, self.params['length'] - len(self.mainMeasures))):
#            self.mainMeasures.append(self.newMeasure())
#
#        self.altEnds[0] = self.mainMeasures[1:]
#        # first make sure there are at least the correct number of alternative endings..
#        for _ in range(max(0, self.params['loop_alt_num'] - len(self.altEnds))):
#            altEnd = [self.newMeasure() for _ in range(self.params['loop_alt_num'])]
#            self.altEnds.append(altEnd)
#
#        # then make sure each alternative end is long enough..
#        for i in range(1, len(self.altEnds)):
#            for _ in range(max(0, self.params['loop_alt_len'] - len(self.altEnds[i]))):
#                self.altEnds[i].append(self.newMeasure())
#
#        if 'transpose_octave' in kwargs:
#            #print('[Section]', 'updated section octave', kwargs['transpose_octave'])
#            for m in self.measures.values():
#                m.setOctave(kwargs['transpose_octave'])
#
#        if 'note_length' in kwargs:
#            #print('[Section]', 'updated note length', kwargs['note_length'])
#            for m in self.measures.values():
#                m.setNoteLength(kwargs['note_length'])
#
#        if 'velocity_range' in kwargs:
#            for m in self.measures.values():
#                m.setVelocities(kwargs['velocity_range'])
#
#        self.flattenMeasures()
#
#    def measureAt(self, n):
#        assert n < len(self.flatMeasures), f'Index {n} for Section {self.name} too large'
#
#        if self.flatMeasures > 0:
#            return self.flatMeasures[n]
#
#        return None
#
#    def flattenMeasures(self):
#        if self.blank:
#            self.flatMeasures = [None]*self.params['length']
#            return
#
#        length = self.params['length']
#        numAlts = self.params['loop_alt_num']
#        lenAlts = self.params['loop_alt_len']
#
#        lenMainMeasures = length - lenAlts
#
#        main = forceListLength(self.mainMeasures, lenMainMeasures)
#
#        track = [None] * (length*self.params['loop_num'])
#
#        for i in range(self.params['loop_num']):
#            track[i*length:i*length+lenMainMeasures] = main
#            if lenAlts > 0:
#                altEnd = self.altEnds[i%numAlts][-lenAlts:]
#                track[i*length+lenMainMeasures:i*length+length] = altEnd
#
#        self.flatMeasures = track
#        self.call()
#
#    def mainLength(self):
#        return self.params['length']
#
#    def getData(self):
#        data = {
#            'name': self.name,
#            'id': self.id_,
#            'params': self.params,
#            'main_measures': [],
#            'alt_ends': [],
#            'measures': dict(),
#            'blank': self.blank
#        }
#
#        for m in self.mainMeasures:
#            if m:
#                data['main_measures'].append(m.id_)
#            else:
#                data['main_measures'].append(None)
#
#        for altEnd in self.altEnds:
#            ae = []
#            for m in altEnd:
#                if m:
#                    ae.append(m.id_)
#                else:
#                    ae.append(None)
#
#            data['alt_ends'].append(ae)
#
#        for mID, measure in self.measures.items():
#            data['measures'][mID] = measure.getData()
#
#        return data
#
#    def setData(self, secData):
#        self.name = secData['name']
#        self.id_ = secData['id']
#        self.params = secData['params']
#        self.mainMeasures = []
#        self.altEnds = []
#        self.measures = dict()
#        self.blank = secData['blank']
#
#        for mID, mData in secData['measures'].items():
#            measure = Measure(mData['id'], notes=mData['notes'])
#            measure.addCallback(self.flattenMeasures)
#            self.measures[int(mID)] = measure
#
#        for mID in secData['main_measures']:
#            if mID == None:
#                self.mainMeasures.append(None)
#            else:
#                self.mainMeasures.append(self.measures[int(mID)])
#
#        for altEnd in secData['alt_ends']:
#            ae = []
#            for mID in altEnd:
#                if mID == None:
#                    ae.append(None)
#                else:
#                    ae.append(self.measures[mID])
#            self.altEnds.append(ae)
#
#        if len(self.measures.keys()) > 0:
#            self.measureCount = max(self.measures.keys()) + 1
#        else:
#            self.measureCount = 0
#
#        self.flattenMeasures()
#
#    def __len__(self):
#        return self.params['length'] * self.params['loop_num']
#
#    def __repr__(self):
#        return f'|{self.name}, {self.params["length"]}'
#
#    def __str__(self):
#        return '|' + ''.join(map(str, self.flatMeasures))


class AISection(SectionBase):
    '''
    Section that has been generated by the AI, so has controls for generation.
    '''

    def __init__(self, name, id_, **kwargs):
        self.altEnds = [[]]
        super().__init__(name, id_, **kwargs)

        self.type_ = 'ai'

    def changeParameter(self, **kwargs):
        super().changeParameter(**kwargs)
        # make sure looping lengths are all correct
        if self.params['loop_alt_len'] >= self.params['length']:
            self.params['loop_alt_len'] = self.params['length'] - 1

        # fill in extra measures
        while len(self.mainMeasures) < self.params['length']:
            self.mainMeasures.append(self.newMeasure())

        self.altEnds[0] = self.mainMeasures[1:]
        # first make sure there are at least the correct number of alternative endings..
        for _ in range(max(0, self.params['loop_alt_num'] - len(self.altEnds))):
            altEnd = [self.newMeasure() for _ in range(self.params['loop_alt_num'])]
            self.altEnds.append(altEnd)

        # then make sure each alternative end is long enough..
        for i in range(1, len(self.altEnds)):
            for _ in range(max(0, self.params['loop_alt_len'] - len(self.altEnds[i]))):
                self.altEnds[i].append(self.newMeasure())


    def newMeasure(self, notes=None, events=None):
        id_ = self.measureCount
        if 'chan' in self.params:
            m = Measure(id_, chan=self.params['chan'], notes=notes, events=events)
        else:
            m = Measure(id_, notes=notes, events=events)

        m.addCallback(self.flattenMeasures)
        self.measures[id_] = m
        self.measureCount += 1
        return m

    def flattenMeasures(self):
        length = self.params['length']
        numAlts = self.params['loop_alt_num']
        lenAlts = self.params['loop_alt_len']

        lenMainMeasures = length - lenAlts

        #main = forceListLength(self.mainMeasures, lenMainMeasures)

        while len(self.mainMeasures) < lenMainMeasures:
            self.mainMeasures.append(self.newMeasure())

        main = self.mainMeasures[:lenMainMeasures]

        track = [None] * (length*self.params['loop_num'])

        for i in range(self.params['loop_num']):
            track[i*length:i*length+lenMainMeasures] = main
            if lenAlts > 0:
                altEnd = self.altEnds[i%numAlts][-lenAlts:]
                track[i*length+lenMainMeasures:i*length+length] = altEnd

        self.flatMeasures = track
        self.call()

    def getData(self):
        data = super().getData()

        data['alt_ends'] = []
        for altEnd in self.altEnds:
            ae = []
            for m in altEnd:
                if m:
                    ae.append(m.id_)
                else:
                    ae.append(None)

            data['alt_ends'].append(ae)

        return data

    def setData(self, secData):
        self.altEnds = []
        for altEnd in secData['alt_ends']:
            ae = []
            for mID in altEnd:
                if mID == None:
                    ae.append(None)
                else:
                    ae.append(self.measures[mID])
            self.altEnds.append(ae)

        super().setData(secData)


class FixedSection(SectionBase):
    '''
    Section that has been read from a file, rather than generated. Therefore no generation parameters
    Parameters:
        length, start measure, repeats?
        velocity, transposition etc.
    '''

    def __init__(self, name, id_, **kwargs):

        super().__init__(name, id_, **kwargs)

        self.type_ = 'fixed'

    def readMidi(self, midiFile, trackNum=0):
        '''TODO: read MIDI data and create measures'''

        # - Find number of measures...
        track = midiFile.tracks[trackNum]
        num_measures = math.ceil(sum(m.time for m in track)/midiFile.ticks_per_beat/4)

        # - Fill in measures
        t = 0
        for msg in track:
            if msg.type not in {'note_on', 'note_off'}:
                continue



class Block:
    '''
    Block: abstract container for sections.
    '''
    def __init__(self, id_, sections=None):
        self.id_ = id_
        if isinstance(sections, list):
            self.sections = sections
        else:
            self.sections = [sections]
        self.flatMeasures = []
        self.flattenMeasures()

    def addSection(self, section):
        self.sections.append(section)
        self.flattenMeasures()

    def flattenMeasures(self):
        self.flatMeasures = []
        for section in self.sections:
            self.flatMeasures.extend(section.flatMeasures)
        return self.flatMeasures

    def getData(self):
        data = {
            'id': self.id_,
            'sections': []
        }

        for section in self.sections:
            data['sections'].append(section.id_)

        return data

    def __len__(self):
        return sum(map(len, self.sections))

    def __repr__(self):
        return f'[{self.id_}: ' + ''.join(map(str, self.sections)) + ']'

    def __getattr__(self, name):
        if name in self.__dict__:
            return self[name]

        try:
            return getattr(self.sections, name)
        except AttributeError:
            raise AttributeError("'{}' object has no attribute '{}'".format(
                self.__class__.__name__, name
            ))


class Instrument:
    def __init__(self, id_, name, chan, engine):
        self.id_ = id_
        self.name = name
        self.chan = chan
        self.engine = engine

        self.sections = dict()
        self.sectionCount = 0

        self.track = Track(self)

        self.mute = False
        self.octave_transpose = 0

    def measuresAt(self, n):
        if self.__len__() == 0:
            return None

        return self.track.measuresAt(n)

    def newSection(self, sectionType='ai', blank=False, **params):
        idx = self.sectionCount
        name = chr(65+idx) + str(self.id_)

        if sectionType == 'ai':
            sectionParams = {**DEFAULT_SECTION_PARAMS, **DEFAULT_AI_PARAMS, **params}
            section = AISection(name, idx, **sectionParams)
        elif sectionType == 'fixed':
            sectionParams = {**DEFAULT_SECTION_PARAMS, **params}
            section = FixedSection(name, idx, **sectionParams)
        else:
            print('[Instrument]', 'Unknown sectionType', sectionType)
            return 0, None

        self.sections[idx] = section
        self.sectionCount += 1
        bar_num = self.track.appendSection(section)
        return bar_num, section

    def duplicateSection(self, id_):
        section = self.sections[id_]
        bar_num = self.track.appendSection(section)
        return bar_num, section

    def compileMidiMessages(self):
        def addEvents(d, n, t, e):
            if n not in events:
                d[n] = dict()

            if t not in events[n]:
                d[n][t] = []

            d[n][t].extend(e)

        events = dict()
        for n, m in enumerate(self.track.flatMeasures):
            if m:
                for t, e in m.getMidiEvents().items():
                    if t >= 96:
                        addEvents(events, n+1, t-96, e)
                    else:
                        addEvents(events, n, t, e)

        return events

    def changeSectionParameters(self, id_, **newParams):
        self.sections[id_].changeParameter(**newParams)
        self.track.flattenMeasures()

    def requestGenerateMeasures(self, sectionID=None, gen_all=False):
        ''' Compiles and sends request for section to generate new bars.
        If no section ID is given, then apply to all sections'''
        if sectionID == None:
            for _, block in self.track.getBlocks():
                for section in block.sections:
                    self.requestGenerateMeasures(sectionID=section.id_, gen_all=gen_all)
            return

        section = self.sections[sectionID]
        sectionStart = self.track.getSectionTimes(sectionID)
        if sectionStart == None:
            print('[Instrument]', 'section start for', section, 'not found...')
            return
        elif section.type_ != 'ai':
            print('[Instrument]', 'section', sectionID, 'is not AI')
            return

        leadID = section.params.get('lead', None)

        for i, m in enumerate(section.flatMeasures):
            if not m:
                print(i, 'm == None')
                continue
            if not gen_all and not m.isEmpty():
                print(i, 'not gen_all and not m.isEmpty()')
                continue
            if m.genRequestSent:
                print(i, 'm.genRequestSent')
                continue

            #request = deepcopy(DEFAULT_SECTION_PARAMS)
            #for k, v in section.params.items():
            #    request[k] = v

            request = {**DEFAULT_SECTION_PARAMS, **DEFAULT_AI_PARAMS, **section.params}

            if leadID and leadID >= 0:
                leadBar = self.engine.measuresAt(leadID, sectionStart+i)
            else:
                leadBar = self.measuresAt(sectionStart+i-1)

            request['lead_bar'] = leadBar
            prev_bars = self.measuresAt(range(sectionStart+i-4, sectionStart+i))
            request['prev_bars'] = prev_bars

            measureAddress = (self.id_, section.id_, m.id_, )
            requires = [b for b in ([leadBar] + request['prev_bars']) if b]

            m.genRequestSent = True

            self.engine.addPendingRequest({
                'request': request,
                'requires': requires,
                'measure_address': measureAddress})

            #print('[Instrument]', 'addedRequest', request)

    def deleteBlock(self, id_):
        self.track.deleteBlock(id_)

    def getData(self):
        data = {
            'id': self.id_,
            'mute': self.mute,
            'octave_transpose': self.octave_transpose,
            'sections': dict(),
            'name': self.name,
            'chan': self.chan
        }

        for id_, section in self.sections.items():
            data['sections'][id_] = section.getData()

        data['track'] = self.track.getData()

        return data

    def setData(self, insData):
        self.id_ = int(insData['id'])
        self.name = insData['name']
        self.chan = insData['chan']
        self.mute = insData['mute']
        self.octave_transpose = insData['octave_transpose']

        self.sections = dict()

        for secID, secData in insData['sections'].items():
            section = Section(secData['name'], secData['id'],
                              blank=secData['blank'], **secData['params'])
            section.setData(secData)
            self.sections[int(secID)] = section

        if len(self.sections.keys()) > 0:
            self.sectionCount = max(self.sections.keys()) + 1
        else:
            self.sectionCount = 0

        self.track = Track(self)
        self.track.setData(insData['track'])

    def __len__(self):
        return len(self.track)

    def __repr__(self):
        return f'{self.id_}, {self.name}, {len(self)} sections, {self.sections.keys()} section IDs'
        #return self.name + ': ' + repr(self.track)


