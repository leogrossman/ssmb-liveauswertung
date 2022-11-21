# -*- coding: utf-8 -*-
"""
Created on Thu May  26 10:13:41 2022

@author: Arnold Kruschinski
"""
import threading
import queue

try:
    from epics import PV
    demo = False
except ModuleNotFoundError:
    demo = True # no epics module, use demo mode which accepts commands but does nothing
    print('Warning: Could not load PyEPICS module, using demo mode (EPICS access disabled).')

def set_PV(pv, data, key, default=0):
    try:
        pv.put(data[key])
    except KeyError: # no data for the given key, set PV to default
        pv.put(default)
    except TypeError: # invalid data, set PV to default
        pv.put(default)

class SSMBPVs:
    '''
    class to access EPICS variables
    '''
    def __init__(self, demo_mode = False):
        self.__demo = demo or demo_mode
        if not self.__demo:
            ### RF frequency readback PV to get bunch spacing
            self.pvfrf = PV('MCLKHGP:rdFrq499')
            
            basic = False # True: val1..val30, False: proper names
            ### PV name fragments ###
            IOC_NAME = 'SCOPE1ZULP' # TBD
            SEP1 = ':'
            H1P = ['h1p1', 'h1p2', 'h1p3']
            H2P = ['h2p1', 'h2p2', 'h2p3']
            SEP2 = ':'
            AMPL_RAW = 'rdAmpl'
            AMPL_AVG = AMPL_RAW + 'Av'
            AMPL_STD = AMPL_RAW + 'Dev'
            TURN_NR = 'rdTurnNr'
            PEAK_NR = 'rdPeakNr'
            
            ### connect to output PVs ###
            # first harmonic #
            self.pvharm1 = [PV(IOC_NAME + SEP1 + HP + SEP2 + AMPL_RAW) for HP in H1P]
            self.pvharm1avg = [PV(IOC_NAME + SEP1 + HP + SEP2 + AMPL_AVG) for HP in H1P]
            self.pvharm1std = [PV(IOC_NAME + SEP1 + HP + SEP2 + AMPL_STD) for HP in H1P]
            self.pvharm1turnnr = [PV(IOC_NAME + SEP1 + HP + SEP2 + TURN_NR) for HP in H1P]
            self.pvharm1peaknr = [PV(IOC_NAME + SEP1 + HP + SEP2 + PEAK_NR) for HP in H1P]
            
            # second harmonic #
            self.pvharm2 = [PV(IOC_NAME + SEP1 + HP + SEP2 + AMPL_RAW) for HP in H2P]
            self.pvharm2avg = [PV(IOC_NAME + SEP1 + HP + SEP2 + AMPL_AVG) for HP in H2P]
            self.pvharm2std = [PV(IOC_NAME + SEP1 + HP + SEP2 + AMPL_STD) for HP in H2P]
            self.pvharm2turnnr = [PV(IOC_NAME + SEP1 + HP + SEP2 + TURN_NR) for HP in H2P]
            self.pvharm2peaknr = [PV(IOC_NAME + SEP1 + HP + SEP2 + PEAK_NR) for HP in H2P]
            
            # laser and general parameters#
            self.pvlaserpos = PV(IOC_NAME + SEP1 + 'rdLaserPos')
            self.pvlasermax = PV(IOC_NAME + SEP1 + 'rdLaserAmpl')
            self.pvavglen   = PV(IOC_NAME + SEP1 + 'rdAvLength')
            self.pvpeakpos  = PV(IOC_NAME + SEP1 + 'rdPeakPos')
            
            ### clear PVs ###
            self.zero()
    
        
    def update(self, peakdata, harm1turns=[1,2,3], harm1peaks=[0,0,0], harm2turns=[1,2,3], harm2peaks=[0,0,0]):
        """
        Update the SSMB PVs with new data.

        Parameters
        ----------
        peakdata : dictionary
            containing the new analyzed SSMB data.
        harm1highturn : int, optional
            turn number for the higher turn plot for the first harmonic. The default is 2.
        harm1lowturnpeak : int, optional
            selected peak number in the analysis for first harmonic, first turn. The default is 0.
        harm1highturnpeak : int, optional
            selected peak number in the analysis for first harmonic, higher turn. The default is 0.
        harm2highturn : int, optional
            turn number for the higher turn plot for the second harmonic. The default is 2.
        harm2lowturnpeak : int, optional
            selected peak number in the analysis for second harmonic, first turn. The default is 0.
        harm2highturnpeak : int, optional
            selected peak number in the analysis for second harmonic, higher turn. The default is 0.
        centerpeak_pos : float, optional
            position of the central peak in the evaluation. The default is None (not plotted).

        Returns
        -------
        None.

        """
        if not self.__demo:
            for t, p, pvraw, pvavg, pvstd, in zip(harm1turns, harm1peaks, self.pvharm1, self.pvharm1avg, self.pvharm1std):
                set_PV(pvraw, peakdata, f'harm1_turn{t-1}_peak{p}')
                set_PV(pvavg, peakdata, f'harm1_turn{t-1}_peak{p}_avg')
                set_PV(pvstd, peakdata, f'harm1_turn{t-1}_peak{p}_std')

            for t, p, pvraw, pvavg, pvstd, in zip(harm2turns, harm2peaks, self.pvharm2, self.pvharm2avg, self.pvharm2std):
                set_PV(pvraw, peakdata, f'harm2_turn{t-1}_peak{p}')
                set_PV(pvavg, peakdata, f'harm2_turn{t-1}_peak{p}_avg')
                set_PV(pvstd, peakdata, f'harm2_turn{t-1}_peak{p}_std')
            
            set_PV(self.pvlaserpos, peakdata, 'laser_position')
            set_PV(self.pvlasermax, peakdata, 'laser_maximum')
            set_PV(self.pvavglen, peakdata, 'averaging_length_harm1') # TODO there are different avglens for harm1,2 in peakdata, can they really be different?
            set_PV(self.pvpeakpos, peakdata, 'centerpeak_pos')
            
    def update_turnparameters(self, harm1turns=[1,2,3], harm1peaks=[0,0,0], harm2turns=[1,2,3], harm2peaks=[0,0,0]):
        """
        Update the SSMB PVs with new turn number and peak number parameters.

        Parameters
        ----------
        harm1highturn : int, optional
            turn number for the higher turn plot for the first harmonic. The default is 2.
        harm1lowturnpeak : int, optional
            selected peak number in the analysis for first harmonic, first turn. The default is 0.
        harm1highturnpeak : int, optional
            selected peak number in the analysis for first harmonic, higher turn. The default is 0.
        harm2highturn : int, optional
            turn number for the higher turn plot for the second harmonic. The default is 2.
        harm2lowturnpeak : int, optional
            selected peak number in the analysis for second harmonic, first turn. The default is 0.
        harm2highturnpeak : int, optional
            selected peak number in the analysis for second harmonic, higher turn. The default is 0.
        centerpeak_pos : float, optional
            position of the central peak in the evaluation. The default is None (not plotted).

        Returns
        -------
        None.

        """
        if not self.__demo:
            for t, p, pvturn, pvpeak, in zip(harm1turns, harm1peaks, self.pvharm1turnnr, self.pvharm1peaknr):
                pvturn.put(t)
                pvpeak.put(p)

            for t, p, pvturn, pvpeak, in zip(harm2turns, harm2peaks, self.pvharm2turnnr, self.pvharm2peaknr):
                pvturn.put(t)
                pvpeak.put(p)
                     
    def zero(self):
        """
        Set all SSMB PVs to zero.

        Returns
        -------
        None.

        """
        if not self.__demo:
            for pvraw, pvavg, pvstd, in zip(self.pvharm1, self.pvharm1avg, self.pvharm1std):
                pvraw.put(0)
                pvavg.put(0)
                pvstd.put(0)

            for pvraw, pvavg, pvstd, in zip(self.pvharm2, self.pvharm2avg, self.pvharm2std):
                pvraw.put(0)
                pvavg.put(0)
                pvstd.put(0)
            
            self.pvlaserpos.put(0)
            self.pvlasermax.put(0)
            self.pvavglen.put(0)
            self.pvpeakpos.put(0)
        
    def get_frf(self):
        """
        return the current RF frequency from EPICS

        Returns
        -------
        float
            the current RF frequency in Hz.

        """
        if self.__demo:
            return None
        else:
            return 499e6 + self.pvfrf.get() * 1e3

class SSMBEpics:
    '''
    Wrapper class to manage the EPICS access for the SSMBLiveEvaluation application
    '''
    def __init__(self, harm1turns=[1,2,3], harm1peaks=[0,0,0], harm2turns=[1,2,3], harm2peaks=[0,0,0], demo_mode=False):
        self.PV = SSMBPVs(demo_mode=demo_mode) # PV access object
        self.data_queue = queue.Queue() # create queue for data input to be written to EPICS
        self.set_turn_parameters(harm1turns, harm1peaks, harm2turns, harm2peaks)
        self.go = False
        self.__thread = threading.Thread(target=self.__pv_loop)
        
    def start(self):
        self.go = True
        self.__thread.start()
    
    def stop(self):
        self.go = False
    
    def set_turn_parameters(self, harm1turns, harm1peaks, harm2turns, harm2peaks):
        self.harm1turns = harm1turns
        self.harm1peaks = harm1peaks
        self.harm2turns = harm2turns
        self.harm2peaks = harm2peaks
        self.PV.update_turnparameters(harm1turns, harm1peaks, harm2turns, harm2peaks)
        
    def __pv_loop(self):
        while self.go:
            try:
                data = self.data_queue.get(timeout = 1) # wait for new data with 1 second timeout to check for self.go
                self.PV.update(data, self.harm1turns, self.harm1peaks, self.harm2turns, self.harm2peaks)
            except queue.Empty:
                pass # no new data, continue waiting.
        
        self.PV.zero() # before quitting, set all PVs to zero
