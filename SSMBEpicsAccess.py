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

class SSMBPVs:
    '''
    class to access EPICS variables
    '''
    def __init__(self):
        if not demo:
            ### RF frequency readback PV to get bunch spacing
            self.pvfrf = PV('MCLKHGP:rdFrq')
            
            ### Output PV name fragments ###
            IOC_NAME = 'SSMB1ZVP' # TBD
            SEP1 = ':'
            H1T1 = 'h1t1'
            H1T2 = 'h1t2'
            H2T1 = 'h2t1'
            H2T2 = 'h2t2'
            SEP2 = ':'
            AMPL_RAW = 'rdAmpl'
            AMPL_AVG = AMPL_RAW + 'Av'
            AMPL_STD = AMPL_RAW + 'Dev'
            TURN_NR = 'rdTurnNr'
            PEAK_NR = 'rdPeakNr'
            
            ### connect to output PVs ###
            # first harmonic #
            self.pvharm1turn1 = PV(IOC_NAME + SEP1 + H1T1 + SEP2 + AMPL_RAW)
            self.pvharm1turn1avg = PV(IOC_NAME + SEP1 + H1T1 + SEP2 + AMPL_AVG)
            self.pvharm1turn1std = PV(IOC_NAME + SEP1 + H1T1 + SEP2 + AMPL_STD)
            self.pvharm1turn1peaknr = PV(IOC_NAME + SEP1 + H1T1 + SEP2 + PEAK_NR)
            self.pvharm1turn2 = PV(IOC_NAME + SEP1 + H1T2 + SEP2 + AMPL_RAW)
            self.pvharm1turn2avg = PV(IOC_NAME + SEP1 + H1T2 + SEP2 + AMPL_AVG)
            self.pvharm1turn2std = PV(IOC_NAME + SEP1 + H1T2 + SEP2 + AMPL_STD)
            self.pvharm1turn2turnnr = PV(IOC_NAME + SEP1 + H1T2 + SEP2 + TURN_NR)
            self.pvharm1turn2peaknr = PV(IOC_NAME + SEP1 + H1T2 + SEP2 + PEAK_NR)
            
            # second harmonic #
            self.pvharm2turn1 = PV(IOC_NAME + SEP1 + H2T1 + SEP2 + AMPL_RAW)
            self.pvharm2turn1avg = PV(IOC_NAME + SEP1 + H2T1 + SEP2 + AMPL_AVG)
            self.pvharm2turn1std = PV(IOC_NAME + SEP1 + H2T1 + SEP2 + AMPL_STD)
            self.pvharm2turn1peaknr = PV(IOC_NAME + SEP1 + H2T1 + SEP2 + PEAK_NR)
            self.pvharm2turn2 = PV(IOC_NAME + SEP1 + H2T2 + SEP2 + AMPL_RAW)
            self.pvharm2turn2avg = PV(IOC_NAME + SEP1 + H2T2 + SEP2 + AMPL_AVG)
            self.pvharm2turn2std = PV(IOC_NAME + SEP1 + H2T2 + SEP2 + AMPL_STD)
            self.pvharm2turn2turnnr = PV(IOC_NAME + SEP1 + H2T2 + SEP2 + TURN_NR)
            self.pvharm2turn2peaknr = PV(IOC_NAME + SEP1 + H2T2 + SEP2 + PEAK_NR)
            
            # laser #
            self.pvlaserpos = PV(IOC_NAME + SEP1 + 'rdLaserPos')
            self.pvlasermax = PV(IOC_NAME + SEP1 + 'rdLaserAmpl')
            
            ### clear PVs ###
            self.zero()
    
        
    def update(self, peakdata, harm1highturn=2, harm1lowturnpeak=0, harm1highturnpeak=0, harm2highturn=2, harm2lowturnpeak=0, harm2highturnpeak=0):
        """
        Update the SSMB PVs with new data.

        Parameters
        ----------
        peakdata : pandas DataFrame
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
        if not demo:
            self.pvharm1turn1.put(peakdata[f'harm1_turn1_peak{harm1lowturnpeak}'])
            self.pvharm1turn1avg.put(peakdata[f'harm1_turn1_peak{harm1lowturnpeak}_avg'])
            self.pvharm1turn1std.put(peakdata[f'harm1_turn1_peak{harm1lowturnpeak}_std'])
            self.pvharm1turn2.put(peakdata[f'harm1_turn{harm1highturn}_peak{harm1highturnpeak}'])
            self.pvharm1turn2avg.put(peakdata[f'harm1_turn{harm1highturn}_peak{harm1highturnpeak}_avg'])
            self.pvharm1turn2std.put(peakdata[f'harm1_turn{harm1highturn}_peak{harm1highturnpeak}_std'])
            
            self.pvharm2turn1.put(peakdata[f'harm2_turn1_peak{harm2lowturnpeak}'])
            self.pvharm2turn1avg.put(peakdata[f'harm2_turn1_peak{harm2lowturnpeak}_avg'])
            self.pvharm2turn1std.put(peakdata[f'harm2_turn1_peak{harm2lowturnpeak}_std'])
            self.pvharm2turn2.put(peakdata[f'harm2_turn{harm2highturn}_peak{harm2highturnpeak}'])
            self.pvharm2turn2avg.put(peakdata[f'harm2_turn{harm2highturn}_peak{harm2highturnpeak}_avg'])
            self.pvharm2turn2std.put(peakdata[f'harm2_turn{harm2highturn}_peak{harm2highturnpeak}_std'])
            
            self.pvlaserpos.put(peakdata['laser_position'])
            self.pvlasermax.put(peakdata['laser_maximum'])
            
    def update_turnparameters(self, harm1highturn=2, harm1lowturnpeak=0, harm1highturnpeak=0, harm2highturn=2, harm2lowturnpeak=0, harm2highturnpeak=0):
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
        if not demo:
            self.pvharm1turn1peaknr.put(harm1lowturnpeak)
            self.pvharm1turn2peaknr.put(harm1highturnpeak)
            self.pvharm1turn2turnnr.put(harm1highturn)
            
            self.pvharm2turn1peaknr.put(harm2lowturnpeak)
            self.pvharm2turn2peaknr.put(harm2highturnpeak)
            self.pvharm2turn2turnnr.put(harm2highturn)
                     
    def zero(self):
        """
        Set all SSMB PVs to zero.

        Returns
        -------
        None.

        """
        if not demo:
            self.pvharm1turn1.put(0)
            self.pvharm1turn1avg.put(0)
            self.pvharm1turn1std.put(0)
            self.pvharm1turn2.put(0)
            self.pvharm1turn2avg.put(0)
            self.pvharm1turn2std.put(0)
            self.pvharm1turn1peaknr.put(0)
            self.pvharm1turn2peaknr.put(0)
            self.pvharm1turn2turnnr.put(0)
            
            self.pvharm2turn1.put(0)
            self.pvharm2turn1avg.put(0)
            self.pvharm2turn1std.put(0)
            self.pvharm2turn2.put(0)
            self.pvharm2turn2avg.put(0)
            self.pvharm2turn2std.put(0)
            self.pvharm2turn1peaknr.put(0)
            self.pvharm2turn2peaknr.put(0)
            self.pvharm2turn2turnnr.put(0)
            
            self.pvlaserpos.put(0)
            self.pvlaserpos.put(0)
        
    def get_frf(self):
        """
        return the current RF frequency from EPICS

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        if demo:
            return None
        else:
            return self.pvfrf.get()

class SSMBEpics:
    '''
    Wrapper class to manage the EPICS access for the SSMBLiveEvaluation application
    '''
    def __init__(self, harm1highturn=2, harm1lowturnpeak=0, harm1highturnpeak=0, harm2highturn=2, harm2lowturnpeak=0, harm2highturnpeak=0):
        self.PV = SSMBPVs() # PV access object
        self.data_queue = queue.Queue() # create queue for data input to be written to EPICS
        self.set_turn_parameters(harm1highturn, harm1lowturnpeak, harm1highturnpeak, harm2highturn, harm2lowturnpeak, harm2highturnpeak)
        self.go = False
        self.__thread = threading.Thread(target=self.__pv_loop)
        
    def start(self):
        self.go = True
        self.__thread.start()
    
    def stop(self):
        self.go = False
    
    def set_turn_parameters(self, harm1highturn, harm1lowturnpeak, harm1highturnpeak, harm2highturn, harm2lowturnpeak, harm2highturnpeak):
        self.harm1highturn = harm1highturn
        self.harm1lowturnpeak = harm1lowturnpeak
        self.harm1highturnpeak = harm1highturnpeak
        self.harm2highturn = harm2highturn
        self.harm2lowturnpeak = harm2lowturnpeak
        self.harm2highturnpeak = harm2highturnpeak
        self.PV.update_turnparameters(harm1highturn, harm1lowturnpeak, harm1highturnpeak, harm2highturn, harm2lowturnpeak, harm2highturnpeak)
        
    def __pv_loop(self):
        while self.go:
            try:
                data = self.data_queue.get(timeout = 1) # wait for new data with 1 second timeout to check for self.go
                self.PV.update(data, self.harm1highturn, self.harm1lowturnpeak, self.harm1highturnpeak, self.harm2highturn, self.harm2lowturnpeak, self.harm2highturnpeak)
            except queue.Empty:
                pass # no new data, continue waiting.
