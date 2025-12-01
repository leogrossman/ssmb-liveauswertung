# -*- coding: utf-8 -*-
"""
Created on Mon May 23 13:50:05 2022

@author: Arnold Kruschinski
"""

import sys
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
    
    def __init__(self, scopeip, data_queue, maxvalue_queue, autoset_time=False):
        """
        Opens a vxi11 connection to the scope at ``scopeip`` and readys the scope control loop in a new thread. Communication via three queues:
         --control_queue: send commands for the scope here in the form ['command', (arguments, ...)] (queue item must be a *list*).
         --status_queue: returns the acquisition status of the scope as (acqstate, acqnumber, savestatus [, self.get_sequence_length])
         --data_queue: here the acquired data is output, in the form (date, data).
         --maxvalue_queue: here the maximum peak height is input for automatic scaling, in the form (harm1, harm2).

        Parameters
        ----------
        scopeip : string
            IP address of the scope that should be connected with.

        """
        sys.path.append('python_vxi11-0.9-py3.6.egg')
        from vxi11 import Instrument
        self.scope = Instrument(scopeip)
        self.channels = ["CH%d" % (i+1) for i in range(4)] # warning: self.channels has to be in increasing order for the code to work! (It is never changed at the moment)
        self.maths = ["MATH%d" % (i+1) for i in range(2)]
        self.__averaginglength = {math: 20 for math in self.maths}
        self.dataranges = None # start with no ranges specified to get full data trace
        self.__trigger_armed = False
        self.go = False
        self.__thread = threading.Thread(target=self.__control_loop)
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
        Start the scope control loop.
        """
        self.go = False
        
    def __control_loop(self):
        i=0
        acqstate = ''
        acqnumber = 0
        savestatus = None
        displaystatus = None
        checkseqlen = False
        scalelen = 20
        scaleauto = [False, False]
        scalechannel = ['CH3', 'CH4'] # TODO this is hard-coded!?
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
                except:
                    print('Warning: There was an error trying to read data from the scope.')
                    try:
                        data = self.get_data()
                        self.__data_queue.put((date, data))
                        print('Retry successful.')
                    except Exception as e:
                        print('Retry failed. Message:')
                        print(type(e), e)
                i = 0 # check for acqusition status immediately after the wait caused by acquiring data!
            
            # then check acquisition status, saving status, and display status
            if i <= 0: # checking aquisition status every 20 loops (200 ms) suffices
                i = 20
                acqstate_new = self.get_acq_status()
                acqnumber_new = self.get_num_acq()
                savestatus_new = self.get_data_saving_status()
                displaystatus_new = self.get_display_status()
                if acqstate != acqstate_new or acqnumber != acqnumber_new or savestatus != savestatus_new or displaystatus != displaystatus_new or checkseqlen:
                    if checkseqlen or acqstate_new == 'SEQUENCE': # also update sequence length when new sequence was started (could have been changed and started on the scope)
                        self.status_queue.put([acqstate_new, acqnumber_new, savestatus_new, displaystatus_new, self.get_sequence_length()])
                        checkseqlen = False
                    else:
                        self.status_queue.put([acqstate_new, acqnumber_new, savestatus_new, displaystatus_new])
                    acqstate = acqstate_new
                    acqnumber = acqnumber_new
                    savestatus = savestatus_new
                    displaystatus = displaystatus_new
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
        Attention: This only works reliably if the method is called repeatedly on a time scale faster than the trigger frequency!
        """
        numacq = int(self.scope.ask('ACQ:NUMACQ?'))
        #state = self.get_trigger_state()
        #if state == "READY" or state == "ARMED":
        #    self.__trigger_armed = True
        #    return False
        #if (state == "TRIGGER" or state == "SAVE") and self.__trigger_armed:
        #    self.__trigger_armed = False
        #    return True
        try:
            numacqchanged = numacq != self.lastnumacq
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
        Returns the data from the last acquisition frame from the scope as a pandas DataFrame with columns: 'TIME', [channel names as given in channel list].
        """
        def decodebinary(binary, datawidth):
            k = 0
            channeldatalist = []
            while k<len(binary):
                if binary[k] == ';': # channels separated by ';', skip this char
                    k += 1
                elif binary[k] == '#': # channel data length coded after '#'
                    k += 1
                    lx = int(binary[k]) # number of data length characters in first character after '#' (this is ASCII!)
                    k += 1
                    ly = int(binary[k:k+lx]) # data length (this is ASCII!)
                    k += lx
                    # After this, read ly bytes of binary data (unsigned int, LSB first) for the current channel:
                    singlechanneldataraw = [sum([ord(binary[j+i])<<(8*i) for i in range(datawidth)]) for j in range(k, k+ly, datawidth)]
                                                                # \ this needs least significant byte first!
                    k += ly
                    channeldatalist.append(singlechanneldataraw)
            return channeldatalist
        
        def transferall(reclen, datawidth):
            self.scope.write('DATA:START 1')
            self.scope.write('DATA:STOP %d' % reclen)
            binary = self.scope.ask('CURVE?', encoding='latin1') # get binary scope data record
            channeldatalist = decodebinary(binary, datawidth)
            channeldf = pd.DataFrame(np.array(channeldatalist).transpose(), columns = self.channels)
            return channeldf
        
        # TODO do we need to do the setup commands every time?
        self.scope.write('DATA:ENC SRP') # unsigned int binary, LSB first
        self.scope.write('DATA:SOURCE ' + ','.join(self.channels))
        reclen = int(self.scope.ask('HOR:MODE:RecordLength?'))
        datawidth = int(self.scope.ask('DATA:WIDTH?')) # number of bytes for each data point
        
        self.scope.write('DATA:START 1')
        self.scope.write('DATA:STOP %d' % reclen)
        xoffset = int(self.scope.ask("WFMOutpre:PT_Off?")) # caution: this is relative to DATA:START -> which should thus be set to 1 before this query is sent
        xscale = float(self.scope.ask("WFMOutpre:XINCR?"))
        
        if self.dataranges is None: # no ranges specified, transfer full trace
            channeldf = transferall(reclen, datawidth)
        
        else: # transfer partial data as given in self.dataranges
            try:
                channeldf = pd.DataFrame(np.zeros((reclen,len(self.channels))), columns=self.channels) # setup DataFrame initialized with zeros
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
                    binary = self.scope.ask('CURVE?', encoding='latin1') # get binary scope data record
                    channeldatalist = decodebinary(binary, datawidth)
                    
                    # insert into DataFrame:
                    channeldf.loc[datastart:datastop] = np.array(channeldatalist).transpose() # use .loc because datastart and datastop are inclusive
                    
            except AssertionError:
                print('Error: Limits for partial scope data transfer are out of bounds! Defaulting to transfering full trace')
                channeldf = transferall(reclen, datawidth)
        
        vertscales  = np.array([self.scope.ask(ch+":SCALE?") for ch in self.channels]).astype(float)
        vertposns   = np.array([self.scope.ask(ch+":POS?") for ch in self.channels]).astype(float)
        scaleddf = (channeldf / 2**(datawidth*8) * 10 - 5 - vertposns) * vertscales
        timeaxis = pd.Series((channeldf.index - xoffset) * xscale, name='TIME')
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
    
    def get_display_status(self):
        chs = {channel: bool(int(self.scope.ask("DISPLAY:GLOBAL:" + channel + ":STATE?"))) for channel in self.channels}
        chs.update({math: bool(int(self.scope.ask("DISPLAY:GLOBAL:" + math + ":STATE?"))) for math in self.maths})
        return chs
    
    def get_math_averaging_length(self):
        return {math: int(self.scope.ask("MATH:" + math + ":AVG:WEIGHT?")) for math in self.maths}
    
    def configure_averaging(self, averaginglength_dict):
        self.__averaginglength.update(averaginglength_dict)
    
    def show_averaging(self, *maths):
        """
        configures averaging length of selected ``maths`` and shows them on the scope screen.
        """
        for math in maths:
            self.scope.write('DISPLAY:GLOBAL:' + math + ':STATE ON')
            self.scope.write('MATH:' + math + ':AVG:MODE ON')
            self.scope.write(format_command('MATH:' + math + ':AVG:WEIGHT', self.__averaginglength[math], form='%d'))
            # the description in the programmer's manual for the :AVG:WEIGHT command is a bit confusing, but it actually seems to be a number of averages
    
    def hide_averaging(self, *maths):
        """
        hides selected ``maths`` on the scope screen.
        """
        for math in maths:
            self.scope.write('DISPLAY:GLOBAL:' + math + ':STATE OFF')
    
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
    
    def increase_scale(self, *channels):
        """
        increases the vertical scale for the given ``channels`` to the next higher scale.
        """
        for channel in channels:
            currentscale = float(self.scope.ask(channel + ":SCALE?"))
            if currentscale < LARGEST_SCALE:
                print('SCOPE: increase scale, channel', channel)
                self.scope.write(format_command(channel + ":SCALE", larger_scale(currentscale)))
        
    def decrease_scale(self, *channels):
        """
        decreases the vertical scale for the given ``channels`` to the next lower scale.
        """
        for channel in channels:
            currentscale = float(self.scope.ask(channel + ":SCALE?"))
            if currentscale > SMALLEST_SCALE:
                print('SCOPE: decrease scale, channel', channel)
                self.scope.write(format_command(channel + ":SCALE", smaller_scale(currentscale)))
                
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
            currentpos = float(self.scope.ask(channel + ":POS?"))
            self.scope.write(format_command(channel + ":POS", currentpos+n_divisions))
            
    def shift_down(self, *channels, n_divisions=0.5):
        """
        shifts the vertical position of the given ``channels`` down by ``n_divisions`` number of divisions
        """
        for channel in channels:
            currentpos = float(self.scope.ask(channel + ":POS?"))
            self.scope.write(format_command(channel + ":POS", currentpos-n_divisions))
    
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
