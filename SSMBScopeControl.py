# -*- coding: utf-8 -*-
"""
Created on Mon May 23 13:50:05 2022

@author: Arnold Kruschinski
"""

import sys
import traceback
import numpy as np
import pandas as pd

import threading
import queue
from time import sleep
from datetime import datetime, timedelta

def format_command(command, argument, form = "%g"):
    return command + " " + form % argument
    
SMALLEST_SCALE = 1e-3 # 1 mV/div
LARGEST_SCALE  = 1    # 1 V/div

SMALLEST_HORIZONTAL_SCALE = 1e-9 # 1 ns/div
LARGEST_HORIZONTAL_SCALE  = 1e-3 # 1 ms/div
    
def larger_scale(scale):
    """
    takes a scale (in V/div) and outputs the next larger (more coarse) scale on the 1,2,5,10... sequence.
    """
    exp = np.floor(np.log10(scale))
    mant = scale/10**exp
    if mant >= 5:
        return   10**(exp+1)
    if mant >= 2:
        return 5*10**exp
    else:
        return 2*10**exp

def smaller_scale(scale):
    """
    takes a scale (in V/div) and outputs the next smaller (more fine) scale on the 1,2,5,10... sequence.
    """
    exp = np.floor(np.log10(scale))
    mant = scale/10**exp
    if mant > 5:
        return 5*10**exp
    if mant > 2:
        return 2*10**exp
    if mant > 1:
        return   10**exp
    else:
        return 5*10**(exp-1)
    
def larger_horizontal_scale(scale):
    """
    takes a scale (in s/div) and outputs the next larger (more coarse) scale on the 1,2,4,10... sequence.
    """
    exp = np.floor(np.log10(scale))
    mant = scale/10**exp
    if mant >= 4:
        return   10**(exp+1)
    if mant >= 2:
        return 4*10**exp
    else:
        return 2*10**exp

def smaller_horizontal_scale(scale):
    """
    takes a scale (in s/div) and outputs the next smaller (more fine) scale on the 1,2,4,10... sequence.
    """
    exp = np.floor(np.log10(scale))
    mant = scale/10**exp
    if mant > 4:
        return 4*10**exp
    if mant > 2:
        return 2*10**exp
    if mant > 1:
        return   10**exp
    else:
        return 4*10**(exp-1)


class SSMBScopeControl:
    
    def __init__(self, scopeip, data_queue, maxvalue_queue, active_channels=['CH1', 'CH2', 'CH3', 'CH4'], active_maths=['MATH1', 'MATH2'], timename='TIME', autoset_time=False):
        """
        Opens a vxi11 connection to the scope at ``scopeip`` and readys the scope control loop in a new thread. Communication via four queues:
         --control_queue: send commands for the scope here in the form ['command', (arguments, ...)] (queue item must be a *list*).
         --status_queue: returns the acquisition status of the scope as (acqstate, acqnumber, savestatus [, self.get_sequence_length])
         --data_queue: here the acquired data is output, in the form (date, data).
         --maxvalue_queue: here the maximum peak height is input for automatic scaling, in the form (harm1, harm2).

        Parameters
        ----------
        scopeip : string
            IP address of the scope that should be connected with.
        data_queue, maxvalue_queue : Queue
            supply theses queues (see above)
        active_channels, active_maths : list[str]
            active channel and math names to be queried from the scope
        timename : str
            name of time column in generated data tables
        autoset_time : bool
            whether to automatically update scope system time on startup

        """
        sys.path.append('python_vxi11-0.9-py3.6.egg')
        from vxi11 import Instrument
        self.scope = Instrument(scopeip)
        self.scope.timeout = 30
        print(self.scope.timeout)
        self.scope.open()
        print(self.scope.client.sock.timeout)
        
        self.channels = sorted(active_channels) # self.channels has to be in increasing order for the code to work! (It is never changed at the moment)
        self.maths = sorted(active_maths)
        self.timename = timename
        self.__averaginglength = {math: 20 for math in self.maths}
        self.dataranges = None # start with no ranges specified to get full data trace
        self.go = False
        self.__thread = threading.Thread(target=self.__control_loop, daemon=True)
        self.control_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.__data_queue = data_queue
        self.__maxvalue_queue = maxvalue_queue
        if autoset_time:
            self.update_system_time()
        
    def start(self):
        """
        Start the scope control loop.
        """
        self.go = True
        self.__thread.start()
        
    def stop(self):
        """
        Stop the scope control loop and close the scope connection.
        """
        self.go = False
        try:
            self.control_queue.put_nowait(['quit'])
        except Exception:
            pass
        if self.__thread.is_alive() and threading.current_thread() is not self.__thread:
            self.__thread.join(timeout=2)
        try:
            self.scope.close()
        except Exception:
            pass
        
    def __control_loop(self):
        i=0
        acqstate = ''
        acqnumber = 0
        savestatus = None
        displaystatus = None
        triggerstatus = None
        triggerflank = None
        mathavglen = None
        checkseqlen = False
        scalelen = 20
        scaleauto = [False, False]
        scalechannel = ['CH3', 'CH4'] # TODO this is hard-coded!? ==> this is just a starting default, will be set properly on autoscale activation
        scalemaxcache = ([],[])
        while self.go:
            while self.control_queue.qsize(): # iterate as long as there are items to get in the control queue
                arguments = self.control_queue.get_nowait()
                command = arguments[0]
                del arguments[0]
                try:
                    if command == 'quit':
                        return # stop control loop on quit command
                    elif command == 'reset':
                        self.recall_setup(*arguments)
                    elif command == 'start':
                        self.start_acq()
                    elif command == 'stop':
                        self.stop_acq()
                    elif command == 'sequence':
                        self.start_acq_sequence(*arguments)
                    elif command == 'seqlen':
                        checkseqlen = True
                    elif command == 'force':
                        self.force_trigger()
                    elif command == 'seqtrig':
                        self.sequence_trigger()
                    elif command == 'normtrig':
                        self.edge_trigger()
                    elif command == 'trigbrise':
                        self.set_trigger_b_flank_rise()
                    elif command == 'trigbfall':
                        self.set_trigger_b_flank_fall()
                    elif command == 'dataranges':
                        self.set_dataranges(*arguments)
                    elif command == 'savestart':
                        self.start_data_saving(*arguments)
                    elif command == 'savestop':
                        self.stop_data_saving()
                    elif command == 'displayon':
                        self.enable_display(*arguments)
                    elif command == 'displayoff':
                        self.disable_display(*arguments)
                    elif command == 'configmath':
                        self.configure_averaging(*arguments)
                    elif command == 'showmath':
                        self.show_averaging(*arguments)
                    elif command == 'hidemath':
                        self.hide_averaging(*arguments)
                    elif command == 'increase':
                        self.increase_scale(*arguments)
                    elif command == 'decrease':
                        self.decrease_scale(*arguments)
                    elif command == 'shiftup':
                        self.shift_up(*arguments)
                    elif command == 'shiftdown':
                        self.shift_down(*arguments)
                    elif command == 'zoomin':
                        self.decrease_horiztonal_scale()
                    elif command == 'zoomout':
                        self.increase_horiztonal_scale()
                    elif command == 'shiftleft':
                        self.shift_left()
                    elif command == 'shiftright':
                        self.shift_right()
                    elif command == 'autoscale':
                        try:
                            scaleauto[arguments[0]] = True
                            scalechannel[arguments[0]] = arguments[1]
                            try:
                                scalelen = arguments[2]
                            except IndexError:
                                pass
                        except IndexError:
                            print('Warning: Setting scope autoscale to automatic failed: No harmonic index given or invalid (must be 0 or 1), or no channel name given')
                    elif command == 'manuscale':
                        try:
                            scalemaxcache[arguments[0]].clear()
                            scaleauto[arguments[0]] = False
                        except IndexError:
                            print('Warning: Setting scope autoscale to manual failed: No harmonic index given or invalid (must be 0 or 1)')
                except (TypeError, ValueError) as e:
                    print(f'Error: ScopeControl: Invalid command "{command}", {arguments}. Error message:')
                    print(type(e), e)
                    
            # once all commands are completed, check for new peak height for automatic scaling
            try:
                maxpeaks = self.__maxvalue_queue.get_nowait()
                for i in range(2): # iterate harmonic 1 and 2
                    if scaleauto[i] and maxpeaks[i] is not None:
                        scalemaxcache[i].append(maxpeaks[i])
                        lendiff = len(scalemaxcache[i]) - scalelen
                        if lendiff > 0:
                            del scalemaxcache[i][0:lendiff]
                        screenmax, smallerscreenmax = self.get_screen_max(scalechannel[i])
                        if maxpeaks[i] > screenmax * .97: # if the current value leaves the screen, scale up immediately. (slready at 97% as clipped values are NaN and would not work)
                            self.increase_scale(scalechannel[i])
                        elif all([mp < smallerscreenmax * .97 for mp in scalemaxcache[i]]): # if over the last scalelen all maxpeaks would have fit on the screen for the next lower scale, scale down.
                            self.decrease_scale(scalechannel[i])
            except queue.Empty:
                pass # no new data, continue
            
            # then check for new data
            if self.check_for_new_acqusition():
                date = datetime.now()
                try:
                    data = self.get_data()
                    self.__data_queue.put((date, data))
                except Exception as e:
                    print('Warning: There was an error trying to read data from the scope. Message:')
                    print(type(e), e)
                    traceback.print_exc()
                i = 0 # check for acqusition status immediately after the wait caused by acquiring data!
            
            # then check acquisition status, saving status, display status, trigger status
            if i <= 0: # checking aquisition status every 20 loops (200 ms) suffices
                i = 20
                acqstate_new = self.get_acq_status()
                acqnumber_new = self.get_num_acq()
                savestatus_new = self.get_data_saving_status()
                displaystatus_new = self.get_display_status()
                triggerstatus_new = self.get_trigger_mode()
                triggerflank_new = self.get_trigger_b_flank()
                mathavglen_new = self.get_math_averaging_length()
                if acqstate != acqstate_new or acqnumber != acqnumber_new or savestatus != savestatus_new or displaystatus != displaystatus_new or triggerstatus != triggerstatus_new or triggerflank != triggerflank_new or mathavglen != mathavglen_new or checkseqlen:
                    if checkseqlen or acqstate_new == 'SEQUENCE': # also update sequence length when new sequence was started (could have been changed and started on the scope)
                        self.status_queue.put([acqstate_new, acqnumber_new, savestatus_new, displaystatus_new, triggerstatus_new, triggerflank_new, mathavglen_new, self.get_sequence_length()])
                        checkseqlen = False
                    else:
                        self.status_queue.put([acqstate_new, acqnumber_new, savestatus_new, displaystatus_new, triggerstatus_new, triggerflank_new, mathavglen_new])
                    acqstate = acqstate_new
                    acqnumber = acqnumber_new
                    savestatus = savestatus_new
                    displaystatus = displaystatus_new
                    triggerstatus = triggerstatus_new
                    triggerflank = triggerflank_new
                    mathavglen = mathavglen_new
            else:
                i -= 1
            sleep(0.01)
            
    def update_system_time(self, timestamp=None, tweak=timedelta(seconds=0)):
        """
        updates system time of the scope with the provided ``timestamp`` (should be datetime object).
        Uses this computer's system time if None provided.
        
        ``tweak`` (timedelta) is added to timestamp to account for transmission delay (default: 0 seconds, only applies for timestamp=None)
        """
        if timestamp is None:
            try:
                target = datetime.now() + tweak
            except:
                target = datetime.now()
        else:
            target = timestamp
        # get date and time currently set on scope:
        scopedate = self.scope.ask('DATE?')
        scopetime = self.scope.ask('TIME?')
        scopedatetime = datetime.strptime('_'.join((scopedate, scopetime)), '"%Y-%m-%d"_"%H:%M:%S"')
        
        if target.date() != scopedatetime.date():
            # the scope is set to a different day than the current day, correcting this is currently not supported
            print('Warning: Scope clock not updated: Scope is not set to the current day!')
            return
        
        delta = (target - scopedatetime).total_seconds()
        hours = abs(delta)/3600
        if hours >= 24:
            print('Warning: Setting scope clock failed (delta too large)!')
            return
        
        # if delta is larger than 1 hour, set time in 1 hour increments
        for h in range(int(hours)):
            if delta < 0:
                hourincrement = scopedatetime - timedelta(minutes = (h+1)*59.9)
            else:
                hourincrement = scopedatetime + timedelta(minutes = (h+1)*59.9)
            self.scope.write(hourincrement.strftime('TIME "%H:%M:%S"'))
            sleep(0.5)
            
        # set target time again for maximum precision and write final timestamp to scope
        if timestamp is None:
            try:
                target = datetime.now() + tweak
            except:
                target = datetime.now()
        else:
            target = timestamp
        self.scope.write(target.strftime('TIME "%H:%M:%S"'))
        
        
        
    
    def recall_setup(self, path_to_setup_file='C:/Scope_Setup/SSMB_standard_20220519.set'):
        """
        recalls the scope setup from a file in scope memory at the given ``path_to_setup_file`` and waits until completion.
        """
        self.scope.write('RECALL:SETUP "%s"' % path_to_setup_file)
        self.scope.ask('*OPC?') # wait until setup is finished
    
    def get_id(self):
        """
        returns the scope device identification code.
        """
        idn = self.scope.ask('*IDN?')
        return idn
        
    def get_trigger_state(self):
        """
        returs the current trigger state as 'TRIGGER', 'READY', 'ARMED', 'AUTO' or 'SAVE'.
        """
        trigstate = self.scope.ask('TRIG:STATE?')
        return trigstate
        
    def check_for_new_acqusition(self):
        """
        checks if there is a new acquisition available since the last check. returns True if this is the case, False otherwise.
        """
        numacq = self.get_num_acq()
        try:
            numacqchanged = numacq > self.lastnumacq
        except:
            numacqchanged = False
        self.lastnumacq = numacq
        return numacqchanged
    
    def get_acq_status(self):
        """
        Returns the acquisition status of the scope, returning either 'RUN', 'STOP' or 'SEQUENCE'.
        """
        seq = self.scope.ask('ACQ:Stopafter?')
        run = self.scope.ask('ACQ:STATE?')
        if (run == 'RUN' or run == '1') and seq == 'SEQUENCE':
            return seq
        else:
            if run == '1':
                return 'RUN'
            if run == '0':
                return 'STOP'
            return run
    
    def get_sequence_length(self):
        """
        Returns the currently set length of the sequence acquisition mode.
        """
        numseq = int(self.scope.ask('ACQ:SEQ:NUMSEQ?'))
        return numseq
    
    def get_num_acq(self):
        """
        Returns the number of acquisitions since the last time a sequence was started or the setup of the scope was changed
        """
        numacq = int(self.scope.ask('ACQ:NUMACQ?'))
        return numacq
    
    def start_acq(self):
        """
        Starts data acquisition on the scope in continuous mode.
        """
        self.scope.write('ACQ:Stopafter RunStop')
        self.scope.write('ACQ:STATE RUN')
    
    def start_acq_sequence(self, numacq=None):
        """
        Starts data acquisition on the scope in sequence mode with maximum ``numacq`` acquisitions. When numacq is not given or None, the previously set value is retained. 
        """
        if numacq is not None:
            self.scope.write(format_command('ACQ:SEQ:NUMSEQ', numacq))
        self.scope.write('ACQ:Stopafter Sequence')
        self.scope.write('ACQ:STATE RUN')
        
    def stop_acq(self):
        """
        Stops data acquisition on the scope.
        """
        self.scope.write('ACQ:STATE STOP')
        
    def force_trigger(self):
        """
        forces a trigger event on the scope.
        """
        self.scope.write('TRIGGER FORCE')
        
    def sequence_trigger(self):
        """
        sets the scope to sequence trigger mode.
        """
        self.scope.write('TRIG:B:STATE ON')

    def edge_trigger(self):
        """
        sets the scope to egde (standard) trigger mode.
        """
        self.scope.write('TRIG:B:STATE OFF')
        
    def get_trigger_mode(self):
        """
        returns True for sequence trigger mode, false for standard trigger mode
        """
        return bool(int(self.scope.ask('TRIG:B:STATE?')))
    
    def set_trigger_b_flank_rise(self):
        """
        sets flank mode for the B trigger to rising
        """
        self.scope.write('TRIG:B:EDGE:SLOPE RISE')
    
    def set_trigger_b_flank_fall(self):
        """
        sets flank mode for the B trigger to falling
        """
        self.scope.write('TRIG:B:EDGE:SLOPE FALL')
    
    def get_trigger_b_flank(self):
        """
        returns flank mode for the B trigger (-1: falling, +1: rising, 0: either)
        """
        flank = self.scope.ask('TRIG:B:EDGE:SLOPE?')
        if flank.upper() == 'RISE': return 1
        if flank.upper() == 'FALL': return -1
        else: return 0
        
    def get_clipping_status(self):
        """
        Returns the clipping status of all active channels (given by the channels list of the scope control object) as a boolean list.
        """
        clipping = [bool(int(self.scope.ask(ch+':Clipping?'))) for ch in self.channels]
        return clipping
    
    def get_screen_max(self, channel):
        """
        Returns the maximum value displayed at the upper limit of the screen for ``channel`` (give channel name) for the current and the next smaller scale
        Returns in the format (currentscale, smallerscale)
        """
        scale = float(self.scope.ask(channel+":SCALE?"))
        position = float(self.scope.ask(channel+":POS?"))
        return (5-position) * scale, (5-position) * smaller_scale(scale)
    
    def set_dataranges(self, dataranges=None):
        """
        set the dataranges to be read for partial data transfer (in seconds relative to trigger). Format: [[range1start, range1stop], [range2start,range2stop], ...]
        """
        self.dataranges = dataranges

    def get_data(self):
        """
        Returns the data from the last acquisition frame from the scope as a pandas DataFrame with columns: self.timename, [self.channels].
        """
        def ask_curve():
            # Read raw waveform bytes directly. Instrument.ask()/read() strips
            # trailing CR/LF characters, which may be valid binary samples.
            self.scope.write('CURVE?')
            raw = self.scope.read_raw()
            print('SCOPE DEBUG: raw CURVE? length =', len(raw))
            print('SCOPE DEBUG: raw CURVE? final bytes =', repr(raw[-10:]))
            return raw.decode('latin1')

        def decodebinary(binary, datawidth):
            k = 0
            channeldatalist = []
            try:
                while k<len(binary):
                    if binary[k] == ';': # channels separated by ';', skip this char
                        k += 1
                    elif binary[k] == '#': # channel data length coded after '#'
                        k += 1
                        if k >= len(binary):
                            raise ValueError("Incomplete binary block header after '#'")
                        lx = int(binary[k]) # number of data length characters in first character after '#' (this is ASCII!)
                        k += 1
                        if k+lx > len(binary):
                            raise ValueError("Incomplete binary block length field")
                        ly = int(binary[k:k+lx]) # data length (this is ASCII!)
                        k += lx
                        if ly % datawidth:
                            raise ValueError("Binary block length is not divisible by DATA:WIDTH")
                        if k+ly > len(binary):
                            raise ValueError("Incomplete binary data block: expected %d bytes, received %d" % (ly, len(binary)-k))
                        # After this, read ly bytes of binary data (unsigned int, LSB first) for the current channel:
                        singlechanneldataraw = [sum([ord(binary[j+i])<<(8*i) for i in range(datawidth)]) for j in range(k, k+ly, datawidth)]
                                                                    # \ this needs least significant byte first!
                        k += ly
                        channeldatalist.append(singlechanneldataraw)
                    else:
                        raise ValueError("Unexpected character in CURVE? response at position %d: %r" % (k, binary[k]))
            except Exception:
                print('SCOPE DEBUG: Failed decoding CURVE? response')
                print('SCOPE DEBUG: response length =', len(binary))
                print('SCOPE DEBUG: response CR count =', binary.count('\r'))
                print('SCOPE DEBUG: response LF count =', binary.count('\n'))
                print('SCOPE DEBUG: parser position =', k)
                print('SCOPE DEBUG: data width =', datawidth)
                print('SCOPE DEBUG: decoded blocks =', len(channeldatalist))
                print('SCOPE DEBUG: response start =', repr(binary[:80]))
                print('SCOPE DEBUG: response end =', repr(binary[-80:]))
                raise
            return channeldatalist

        def transferall(reclen, datawidth, transferred_channels):
            self.scope.write('DATA:START 1')
            self.scope.write('DATA:STOP %d' % reclen)
            for attempt in range(2):
                try:
                    binary = ask_curve() # get binary scope data record without stripping valid CR/LF bytes
                    channeldatalist = decodebinary(binary, datawidth)
                    if len(channeldatalist) != len(transferred_channels):
                        raise ValueError("Expected %d channel blocks, received %d" % (len(transferred_channels), len(channeldatalist)))
                    channeldf = pd.DataFrame(np.array(channeldatalist).transpose(), columns = transferred_channels)
                    return channeldf
                except (IndexError, ValueError) as e:
                    print('SCOPE DEBUG: CURVE? transfer attempt %d failed: %s' % (attempt+1, e))
                    print('SCOPE DEBUG: record length =', reclen)
                    print('SCOPE DEBUG: transferred channels =', transferred_channels)
                    if attempt == 0:
                        print('SCOPE DEBUG: retrying CURVE? transfer once')
                    else:
                        raise
        
        active_channels = self.get_active_channels()
        self.scope.write('DATA:ENC SRP') # unsigned int binary, LSB first
        self.scope.write('DATA:SOURCE ' + ','.join(active_channels))
        reclen = int(self.scope.ask('HOR:MODE:RecordLength?'))
        datawidth = int(self.scope.ask('DATA:WIDTH?')) # number of bytes for each data point
        
        self.scope.write('DATA:START 1') # these commands for START/STOP seem duplicate, but are needed for partial data transfer to work properly... (somewhat unclear why)
        self.scope.write('DATA:STOP %d' % reclen)
        xoffset = int(self.scope.ask("WFMOutpre:PT_Off?")) # caution: this is relative to DATA:START -> which should thus be set to 1 before this query is sent
        xscale = float(self.scope.ask("WFMOutpre:XINCR?"))
        
        if self.dataranges is None: # no ranges specified, transfer full trace
            channeldf = transferall(reclen, datawidth, active_channels)
        
        else: # transfer partial data as given in self.dataranges
            try:
                channeldf = pd.DataFrame(np.zeros((reclen,len(active_channels))), columns=active_channels) # setup DataFrame initialized with zeros
                for datarange in self.dataranges: # iteration over individual ranges
                    # dataranges are specified in TIME, convert to sample indices
                    # add 1 because DATA:START/STOP range from 1 to reclen
                    datastart = datarange[0] // xscale + xoffset + 1
                    datastop  = datarange[1] // xscale + xoffset + 1
                    assert datastart >= 1
                    assert datastop <= reclen
                    # TODO we can have some data ranges that are outside the bounds and should just be ignored gracefully!
                    
                    # get data:
                    self.scope.write('DATA:START %d' % datastart)
                    self.scope.write('DATA:STOP %d' % datastop)
                    binary = ask_curve() # get binary scope data record without stripping valid CR/LF bytes
                    channeldatalist = decodebinary(binary, datawidth)
                    
                    # insert into DataFrame:
                    channeldf.loc[datastart:datastop] = np.array(channeldatalist).transpose() # use .loc because datastart and datastop are inclusive
                    
            except AssertionError:
                print('Error: Limits for partial scope data transfer are out of bounds! Defaulting to transfering full trace')
                channeldf = transferall(reclen, datawidth, active_channels)
        
        vertscales  = np.array([self.scope.ask(ch+":SCALE?") for ch in active_channels]).astype(float)
        vertposns   = np.array([self.scope.ask(ch+":POS?") for ch in active_channels]).astype(float)
        scaleddf = (channeldf / 2**(datawidth*8) * 10 - 5 - vertposns) * vertscales
        timeaxis = pd.Series((channeldf.index - xoffset) * xscale, name=self.timename)
        return pd.concat((timeaxis, scaleddf), axis='columns')
    
    def start_data_saving(self, path, filename, savebinary=True, saveimage=False):
        self.scope.write(f'SAVEON:FILE:DEST "{path}"')
        self.scope.write(f'SAVEON:FILE:NAME "{filename}"')
        if saveimage:
            self.scope.write('SAVEON:IMAGE:FILEF PNG')
        self.scope.write('SAVEON:IMAGE %d' % saveimage)
        self.scope.write('SAVEON:WAVE:FILEF ' + 'INTERN' if savebinary else 'SPREADSHEET')
        self.scope.write('SAVEON:WAVE:SOURCE ALL')
        self.scope.write('SAVEON:WAVE ON')
        print(f'SCOPE: start data saving as "{filename}" at {path}')
        self.scope.write('SAVEON:TRIG ON')
    
    def stop_data_saving(self):
        print('SCOPE: stop data saving')
        self.scope.write('SAVEON:TRIG OFF')
    
    def get_data_saving_status(self):
        savestate = bool(int(self.scope.ask('SAVEON:TRIG?')))
        return savestate
    
    def get_data_saving_path(self):
        savepath = self.scope.ask("SAVEON:FILE:DEST?").strip('"')
        return savepath
    
    def get_data_saving_name(self):
        savename = self.scope.ask("SAVEON:FILE:NAME?").strip('"')
        return savename
    
    def get_active_channels(self):
        allactiveset = set(self.scope.ask('DATA:SOURCE:AVAILABLE?').upper().split(','))
        return sorted(list(allactiveset.intersection(set(self.channels))))
    
    def get_active_maths(self):
        allactiveset = set(self.scope.ask('MATH:LIST?').upper().split(','))
        return sorted(list(allactiveset.intersection(set(self.maths))))
    
    def get_display_status(self):
        chs = {channel: bool(int(self.scope.ask("DISPLAY:GLOBAL:" + channel + ":STATE?"))) for channel in self.channels}
        chs.update({math: bool(int(self.scope.ask("DISPLAY:GLOBAL:" + math + ":STATE?"))) for math in self.get_active_maths()})
        return chs
    
    def get_math_averaging_length(self):
        return {math: int(self.scope.ask("MATH:" + math + ":AVG:WEIGHT?")) for math in self.get_active_maths()}
    
    def configure_averaging(self, averaginglength_dict):
        self.__averaginglength.update(averaginglength_dict)
    
    def show_averaging(self, *maths):
        """
        configures averaging length of selected ``maths`` and shows them on the scope screen.
        """
        try:
            for math in maths:
                self.scope.write('DISPLAY:GLOBAL:' + math + ':STATE ON')
                self.scope.write('MATH:' + math + ':AVG:MODE ON')
                self.scope.write(format_command('MATH:' + math + ':AVG:WEIGHT', self.__averaginglength[math], form='%d'))
                # the description in the programmer's manual for the :AVG:WEIGHT command is a bit confusing, but it actually seems to be a number of averages
        except: #TODO specify error type?
            print('Warning: failed to activate math channel, not configured?')
    
    def hide_averaging(self, *maths):
        """
        hides selected ``maths`` on the scope screen.
        """
        try:
            for math in maths:
                self.scope.write('DISPLAY:GLOBAL:' + math + ':STATE OFF')
        except: #TODO specify error type?
            print('Warning: failed to hide math channel, not configured?')

    def enable_display(self, *channels):
        """
        enables display of selected ``channels`` on the scope screen.
        """
        for channel in channels:
            self.scope.write('DISPLAY:GLOBAL:' + channel + ':STATE ON')
    
    def disable_display(self, *channels):
        """
        disables display of selected ``channels`` on the scope screen.
        """
        for channel in channels:
            self.scope.write('DISPLAY:GLOBAL:' + channel + ':STATE OFF')


    '''
    the functions increase/deacrease_scale and shift_up/down    
    now use the commands
    DISplay:WAVEView<x>:MATH:MATH<x>:VERTical:POSition
    DISplay:WAVEView<x>:MATH:MATH<x>:VERTical:SCAle
    and    
    DISplay:WAVEView1:CH<1>:VERTical:POSition
    DISplay:WAVEView1:CH<1>:VERTical:SCAle
    to enable functionality for MATH channels as well.
    These seem to work for WAVEView1. and appear identical to the CH<x>:SCALE/POS commands for the raw channels. Unclear when other WAVEViews may be used... So look here for unexpected behaviour...    
    '''
    
    def increase_scale(self, *channels):
        """
        increases the vertical scale for the given ``channels`` to the next higher scale.
        """
        for channel in channels:
            if 'MATH' in channel.upper():
                channel = 'MATH:' + channel
            currentscale = float(self.scope.ask("DISPLAY:WAVEView1:" + channel + ":VERTICAL:SCALE?"))
            if currentscale < LARGEST_SCALE:
                try:
                    self.scope.write(format_command("DISPLAY:WAVEView1:" + channel + ":VERTICAL:SCALE", larger_scale(currentscale)))
                    print('SCOPE: increase scale, channel', channel)
                except: #TODO specify error type?
                    print(f'Warning: failed to scale channel {channel}, not configured?')

        
    def decrease_scale(self, *channels):
        """
        decreases the vertical scale for the given ``channels`` to the next lower scale.
        """
        for channel in channels:            
            if 'MATH' in channel.upper():
                channel = 'MATH:' + channel
            currentscale = float(self.scope.ask("DISPLAY:WAVEView1:" + channel + ":VERTICAL:SCALE?"))
            if currentscale > SMALLEST_SCALE:
                try:
                    self.scope.write(format_command("DISPLAY:WAVEView1:" + channel + ":VERTICAL:SCALE", smaller_scale(currentscale)))
                    print('SCOPE: decrease scale, channel', channel)
                except: #TODO specify error type?
                    print(f'Warning: failed to scale channel {channel}, not configured?')
                
    def increase_horiztonal_scale(self):
        """
        increases the horiztonal scale to the next higher scale.
        """
        currentscale = float(self.scope.ask("HOR:SCALE?"))
        if currentscale < LARGEST_HORIZONTAL_SCALE:
            print('SCOPE: increase horizontal scale')
            self.scope.write(format_command("HOR:SCALE", larger_horizontal_scale(currentscale)))
        
    def decrease_horiztonal_scale(self):
        """
        decreases the horiztonal scale to the next lower scale.
        """
        currentscale = float(self.scope.ask("HOR:SCALE?"))
        if currentscale > SMALLEST_HORIZONTAL_SCALE:
            print('SCOPE: decrease horizontal scale')
            self.scope.write(format_command("HOR:SCALE", smaller_horizontal_scale(currentscale)))
    
    def shift_up(self, *channels, n_divisions=0.5):
        """
        shifts the vertical position of the given ``channels`` up by ``n_divisions`` number of divisions
        """
        for channel in channels:            
            if 'MATH' in channel.upper():
                channel = 'MATH:' + channel
            currentpos = float(self.scope.ask("DISPLAY:WAVEView1:" + channel + ":VERTICAL:POS?"))
            self.scope.write(format_command("DISPLAY:WAVEView1:" + channel + ":VERTICAL:POS", currentpos+n_divisions))
            
    def shift_down(self, *channels, n_divisions=0.5):
        """
        shifts the vertical position of the given ``channels`` down by ``n_divisions`` number of divisions
        """
        for channel in channels:            
            if 'MATH' in channel.upper():
                channel = 'MATH:' + channel
            currentpos = float(self.scope.ask("DISPLAY:WAVEView1:" + channel + ":VERTICAL:POS?"))
            self.scope.write(format_command("DISPLAY:WAVEView1:" + channel + ":VERTICAL:POS", currentpos-n_divisions))
    
    def shift_left(self, screen_percent=5):
        """
        shifts the horizontal position left by ``screen_percent`` % of the screen width
        """
        currentpos = float(self.scope.ask("HOR:POS?"))
        self.scope.write(format_command("HOR:POS", currentpos-screen_percent))
            
    def shift_right(self, screen_percent=5):
        """
        shifts the horizontal position right by ``screen_percent`` % of the screen width
        """
        currentpos = float(self.scope.ask("HOR:POS?"))
        self.scope.write(format_command("HOR:POS", currentpos+screen_percent))
