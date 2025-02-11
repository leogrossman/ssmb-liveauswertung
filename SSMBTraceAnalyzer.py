# -*- coding: utf-8 -*-
"""
Created on Wed Jul  7 15:13:29 2021

@author: Arnold Kruschinski
"""

import numpy as np
import pandas as pd
from scipy.ndimage import median_filter

import TektronixWfmImport as tek

class TraceAnalyzer:
    
    def __init__(self, data=None, filepath=None, frf = 499.7e6, windowcenter_ns = 10, windowwidth_ns = 20,
                 timecolumnname = "TIME", harm1columnname = "CH3", harm2columnname = "CH4", lasercolumnname = "CH1", invertharm1 = False, invertharm2 = False, invertlaser = False):
        """
        Initialize the Trace data from ``filepath`` or provide the ``data`` and define the ``windowcenter_ns`` and ``windowwidth_ns`` where the first turn signal is expected.

        Parameters
        ----------
        data : pandas DataFrame, optional
            Directly give the trace data. The default is None (use provided file).
        filepath : str or list of str, optional
            If data=None, path to the file from where to import the tracedata. must be '.csv' of '.wfm'. If list of file paths, must be '.wfm' files to multiple channels of the same measurement. The default is None (use directly provided data).
        frf : float, optional
            masterclock frequency of the measurement in Hz. The default is 499.7e6 (None also gives 499.7e6).
        windowcenter_ns : float, optional
            center of the first turn window relative to the trigger (t=0) in ns. The default is 10.
        windowwidth_ns : float, optional
            width of the data window around each turn in nanoseconds. The default is 20.
        timecolumnname : str, optional
            Name of the time column in the provided data set. The default is "TIME".
        harm1columnname : str, optional
            Name of the first harmonic signal column in the provided data set. The default is "CH3".
        harm2columnname : str, optional
            Name of the second harmonic signal column in the provided data set. The default is "CH4".
        invertharm1 : bool, optional
            If True, invert the values for the first harmonic column. The default is False.
        invertharm2 : bool, optional
            If True, invert the values for the second harmonic column. The default is False.
        
        Raises
        ------
        RuntimeError
            if neither trace data nor filepath are provided.
            if the provided first turn window is not located within the data trace.
        FileNotFoundError
            if the provided file is not .csv or .wfm

        Returns
        -------
        None.

        """
        if frf is None:
            self.frf = 499.7e6
        else:
            self.frf = frf
        self.timecolumn = timecolumnname
        self.harm1column = harm1columnname
        self.harm2column = harm2columnname
        self.lasercolumn = lasercolumnname
        
        self.trace = None
        self.bgcorrectedtraces1 = None
        self.bgaveragetraces1 = None
        self.bgcorrectedtraces2 = None
        self.bgaveragetraces2 = None
        if data is not None:
            self.trace = data
        elif filepath is not None:
            self.read_data(filepath)
        else:
            raise RuntimeError("Neither trace data nor filepath provided!")
        
        if not( self.harmonic_exists(1) or self.harmonic_exists(2) ):
            raise RuntimeError("There are no data columns matching either first or second harmonic column names")
        
        try:
            if invertharm1:
                self.trace[self.harm1column] *= -1
        except KeyError:
            print("Warning: Tried to invert nonexistent first harmonic column")
        try:
            if invertharm2:
                self.trace[self.harm2column] *= -1
        except KeyError:
            print("Warning: Tried to invert nonexistent second harmonic column")
        try:
            if invertlaser:
                self.trace[self.lasercolumn] *= -1
        except KeyError:
            print("Warning: Tried to invert nonexistent laser monitoring column")
            
        self.timeresolution = self.trace[self.timecolumn][1] - self.trace[self.timecolumn][0]
        self.triggerpos = int(round(-self.trace[self.timecolumn][0]/self.timeresolution))
        self.windowstart = self.triggerpos  + self.time_to_points(windowcenter_ns) - self.time_to_points(windowwidth_ns/2)
        self.windowend   = self.windowstart + self.time_to_points(windowwidth_ns)
        self.maxpeakexclusion = 0
        try:
            self.trace.loc[self.windowstart]
            self.trace.loc[self.windowend]
        except KeyError:
            raise RuntimeError("the provided first turn window is not located within the data trace!")
                
    def read_data(self, filepath):
        '''
        Import .csv or tektronix .wfm file with oscilloscope data into self.trace as pandas DataFrame.
        
        Parameters
        ----------
        filepath : string or list of strings
            Path to the file from where to import the tracedata. must be '.csv' of '.wfm'. If list of file paths, must be '.wfm' files to multiple channels of the same measurement.
        '''
        if type(filepath) is not str:
            self.trace = tek.read_multi_channel(filepath)
        elif filepath[::-1].find('mfw.') == 0: # if filepath ends with '.wfm'
            self.trace = tek.read_single_channel(filepath)
        
        elif filepath[::-1].find('vsc.') == 0: # if filepath ends with '.csv'
            for i in range(11,-1,-1): # number of header rows should be 11, but could be less for single column files
                try:
                    self.trace = pd.read_csv(filepath, skiprows = i)
                except pd.errors.EmptyDataError:
                    raise RuntimeError("csv import failed, no data in file")
                try:
                    self.trace[self.timecolumn] # this fails with KeyError if "timecolum" key not present, which means we have skipped to many rows
                    return
                except KeyError:
                    print("Warning: csv import fail, reducing skiprows to", i-1)
            raise RuntimeError("csv import failed, could not resolve column names")
        
        else:
            raise FileNotFoundError("Provided file is not .csv or .wfm")
    
    def harmonic_exists(self, harmonic = 1):
        """
        Checks if a column of data exists for the specified harmonic.
        
        Parameters
        ----------
        harmonic : int, optional
            Number of harmonic (1,2,...). The default is 1.
            
        Returns
        -------
        bool
            True if column exists, False otherwise.
        """
        if harmonic == 1:
            datacolumn = self.harm1column
        elif harmonic == 2:
            datacolumn = self.harm2column
        else:
            return False
        try:
            self.trace[datacolumn]
            return True
        except KeyError:
            return False
            #raise RuntimeError(f"There is no data column matching the specified first harmonic column name ({self.harm1column})!")
        
    
    def get_horizontal_info(self):
        """
        Get horizontal (timing) information from the stored trace.
        
        Returns
        -------
        float
            start time of stored trace (s).
        float
            time increment of stored trace (s).
        int
            number of points in stored trace.

        """
        return self.trace[self.timecolumn][0], self.timeresolution, len(self.trace)
    
    
    def compare_horizontal_info(self, starttime, incrementtime, numpoints):
        """
        Compares the given horizontal information with the stored trace and returns if the horizontal scales are equal.

        Parameters
        ----------
        starttime : float
            start time of dataset (s).
        incrementtime : float
            time increment of dataset (s).
        numpoints : int
            number of points in dataset.

        Returns
        -------
        boolean
            True if given horizontal info and stored trace are equal.

        """
        selfstarttime, selfincrementtime, selfnumpoints = self.get_horizontal_info()
        startok = abs(selfstarttime - starttime) < 1e-9
        incrementok = abs(selfincrementtime - incrementtime) < 1e-11
        numpointsok = selfnumpoints == numpoints
        return startok and incrementok and numpointsok
    
    
    def points_to_time(self, points, absolute = False):
        """
        Get the time in nanoseconds corresponding to the given number of data ``points``on the current data trace.

        Parameters
        ----------
        points : index
            number of data points.
        absolute: bool, optional
            If True, time is calculated for an absolute index point, i.e. relative to the trigger position. If False, the time corresponding to a relative number of index points is returned. The default is False.
            
        Returns
        -------
        float
            time in nanoseconds corresponding to ``points``.
        """
        absolute_offset = self.trace[self.timecolumn][0] if absolute else 0
        return points * self.timeresolution /1e-9 + absolute_offset
    
    def time_to_points(self, time_ns):
        """
        Get the number of data points corresponding to ``time_ns`` on the current data trace.

        Parameters
        ----------
        bgfit = self.calc_bg_fit(turn, fitwidth_ns, fitorder)
        time_ns : float
            time in nanoseconds.

        Returns
        -------
        int
            number of points corresponding to ``time_ns``.
        """
        return int(round(time_ns*1e-9 / self.timeresolution))
    
    def bunch_gap_points(self, nbunches = 1):
        """
        Get the number of data points corresponding to the time between ``nbunches`` on the current data trace.

        Parameters
        ----------
        nbunches : float
            number of bunches. Can be fractional. The default is 1.

        Returns
        -------
        int
            number of points corresponding to ``time_ns``.
        """
        return int(round(nbunches / self.frf / self.timeresolution))
    
    
    def get_window(self, turn = 0):
        """
        Get the start end end indices of the data window for the given ``turn``

        Parameters
        ----------
        turn : int, optional
            index of the turn. The default is 0.

        Returns
        -------
        int
            start index of the window for the given turn.
        int
            end index of the window for the given turn.

        """
        turndiff = self.bunch_gap_points(80) * turn
        return self.windowstart + turndiff, self.windowend + turndiff
    
    def get_window_times(self, turn = 0):
        """
        Get the start end end times in nanoseconds of the data window for the given ``turn``.
        This is more robust than using trace[timecolumn][windowstart/end_index] as this function does not require there to be actual data at that time.

        Parameters
        ----------
        turn : int, optional
            index of the turn. The default is 0.

        Returns
        -------
        float
            start time of the window for the given turn.
        float
            end time of the window for the given turn.

        """
        zerotime = self.get_horizontal_info()[0] * 1e9
        windowstart, windowend = self.get_window(turn)
        return zerotime + self.points_to_time(windowstart), zerotime + self.points_to_time(windowend)
    
    def get_extended_window(self, turn = 0, extension_ns = 10):
        """
        Get the start end end indices of the data window for the given ``turn``, extended by ``extension_ns``

        Parameters
        ----------
        turn : int, optional
            index of the turn. The default is 0.
        extension_ns : float, optional
            time in nanoseconds to extend the data window in both directions. The default is 10.

        Returns
        -------
        int
            start index of the extended window for the given turn.
        int
            end index of the extended window for the given turn.

        """
        turndiff = self.bunch_gap_points(80) * turn
        extension = self.time_to_points(extension_ns)
        return self.windowstart + turndiff - extension, self.windowend + turndiff + extension
        
    
    def calc_bg_fit(self, turn = 0, fitwidth_ns = 10, order=1, harmonic = 1):
        datacolumn = self.harm2column if harmonic == 2 else self.harm1column
        
        windowstart, windowend = self.get_window(turn)
        windowstartext, windowendext = self.get_extended_window(turn, fitwidth_ns)
        lefttrace = self.trace[windowstartext:windowstart]
        assert len(lefttrace) > 0
        righttrace= self.trace[windowend:windowendext]
        assert len(righttrace) > 0
        fittrace  = pd.concat([lefttrace, righttrace])
        assert len(fittrace) > order
        return np.polyfit(fittrace[self.timecolumn], fittrace[datacolumn], order)
    
    def calc_bg_correct(self, turn = 0, filtering=False, filterwidth = 51, fitwidth_ns = 10, fitorder=1, harmonic = 1):
        datacolumn = self.harm2column if harmonic == 2 else self.harm1column
        
        windowtrace = self.trace[slice(*self.get_window(turn))].copy()
        if filtering:
            filtered = median_filter(windowtrace[datacolumn], filterwidth)
            windowtrace[datacolumn] -= filtered
        else:
            bgfit = self.calc_bg_fit(turn, fitwidth_ns, fitorder, harmonic)
            windowtrace[datacolumn] -= np.polyval(bgfit, windowtrace[self.timecolumn])
        return windowtrace
    
    def do_bg_correct(self, filtering = False, filterwidth_ns = 2, maxturns = 10, fitwidth_ns = 10, fitorder=1, maxharmonic = 2):
        """
        Do the background correction fits for up to ``maxturns`` turns, storing the resulting background corrected traces.

        Parameters
        ----------
        filtering: bool, optional
            If True, use a median filter to obtain the background correction, otherwise use linear fit as specified below. The default is False.
        filterwidth_ns : float, optional
            Width of the median filter in ns. Ignored if fitting is chosen. The default is 2.
        maxturns : int, optional
            The number of turns for which to conduct background correction. The default is 10.
        fitwidth_ns : float, optional
            Width of data in ns beyond both borders of the turn window where the background fit is done. Ignored if filtering is chosen. The default is 10.
        fitorder : int, optional
            Order of the polynomial fit to apply. Ignored if filtering is chosen. The default is 1.
        maxharmonic : int, optional
            Maximum number of harmonic (1,2,...) for which to do bg correction. The default is 2.

        Returns
        -------
        None.

        """
        mh = 2 if maxharmonic >= 2 else 1
        filterwidth = self.time_to_points(filterwidth_ns)
        if filterwidth%2 == 0:
            filterwidth += 1 # filterwidth should be odd
            
        if filtering:
            self.maxpeakexclusion = filterwidth
        
        for harmonic in range(1,mh+1):
            if self.harmonic_exists(harmonic):
                bgcorrectedtraces = []
                try:
                    for t in range(maxturns):
                        bgcorrectedtraces.append(self.calc_bg_correct(t, filtering, filterwidth, fitwidth_ns, fitorder, harmonic))
                        # ^ raises AssertionError (from calc_bg_fit) if there is not enough data for the bg fit at turn t
                    if harmonic == 2:
                        self.bgcorrectedtraces2 = bgcorrectedtraces                
                    else:
                        self.bgcorrectedtraces1 = bgcorrectedtraces
                except AssertionError:
                    if len(bgcorrectedtraces) > 0:# if there are bgcorrectedtraces obtained for lower turns, just keep these.
                        if harmonic == 2:
                            self.bgcorrectedtraces2 = bgcorrectedtraces                
                        else:
                            self.bgcorrectedtraces1 = bgcorrectedtraces
                    else:
                        raise RuntimeError("background fit failed for the first turn due to insufficient data points")
                    #TODO do bgcorrectedtraces1/2 both contain all data columns?!? Is this needed somewhere?
        
    def get_bg_corrected_trace(self, turn = 0, harmonic = 1):
        if harmonic == 2:
            return self.bgcorrectedtraces2[turn]
        return self.bgcorrectedtraces1[turn]
    
        
    def do_averaging(self, tracecache):
        """
        Calculate and store the averaged traces for all available turns.

        Parameters
        ----------
        tracecache : list of list of list of pandas dataframes
            containing the the background corrected traces of the previous measurements. Inner list: turns. Middle list: measurements. Outer list: Harmonics.

        Returns
        -------
        None.

        """
        for iharmonic, cache in enumerate(tracecache):
            if self.harmonic_exists(iharmonic+1):
                datacolumn = self.harm2column if iharmonic == 1 else self.harm1column
                
                bgavgtraces = []
                for t, bgcorrectedtrace in enumerate(self.bgcorrectedtraces2 if iharmonic == 1 else self.bgcorrectedtraces1):
                    cachetraces = []
                    for c in cache:
                        try:
                            cachetraces.append(c[t])
                        except IndexError:
                            pass # ignore missing data in cache, just use less measurements for averaging.
                    cachetraces.append(bgcorrectedtrace)
                    cacheconcat = pd.concat(cachetraces)
                    cachegroup  = cacheconcat[[self.timecolumn,datacolumn]].groupby(cacheconcat.index)
                    bgavgtrace  = cachegroup.mean()
                    bgavgtraces.append(bgavgtrace)
                if iharmonic == 1:
                    self.bgaveragetraces2 = bgavgtraces
                else:
                    self.bgaveragetraces1 = bgavgtraces
        
    def get_averaged_bg_corrected_trace(self, turn = 0, harmonic = 1):
        if harmonic == 2:
            return self.bgaveragetraces2[turn]   
        return self.bgaveragetraces1[turn]
    
    def get_laser_maximum(self, minimum_signal = 0.03):
        """
        Get the value and position of the maximum of the laser monitoring signal (over the complete trace).

        Parameters
        ----------
        minimum_signal: float, optional
            minimum value in volts the maximum of the laser monitoring signal must have in order to be returned (useful if there is only noise to supress erroneous information). The default is 0.03.
        
        Returns
        -------
        float, float
            the maximum value of the laser monitoring signal and its position within the trace in ns.

        """
        try:
            lasermax = max(self.trace[self.lasercolumn])
        except KeyError:
            # there is no data for the laser monitoring column.
            return np.nan, np.nan
        if lasermax < minimum_signal:
            # maximum of laser monitoring signal is below specified threshold.
            return np.nan, np.nan
        lasermaxpos = self.trace[self.timecolumn].loc[self.trace[self.lasercolumn] == lasermax].iloc[0]*1e9 #s to ns
        return lasermax, lasermaxpos
        

    def get_max_peak(self, turn = 0, average = False, harmonic = 1):
        """
        Get the value of the highest peak within the ``turn`` window.

        Parameters
        ----------
        turn : int, optional
            index of the turn where to obtain the peak. The default is 0.
        average : bool, optional
            If True, get peaks from the averaged traces (have to be generated by calling "do_averaging"). The default is False.
        harmonic : int, optional
            Number of harmonic (1,2,...). The default is 1.
        
        Returns
        -------
        float
            the value of the highest peak within the window.

        """
        
        # here, use maxpeakexclusion to not use the edges of the window for determining the max peak height, as there might be filtering artifacts here
        if average:
            try:
                return max(self.bgaveragetraces2[turn].iloc[self.maxpeakexclusion:-self.maxpeakexclusion-1][self.harm2column] if harmonic == 2 else self.bgaveragetraces1[turn][self.harm1column].iloc[self.maxpeakexclusion:-self.maxpeakexclusion-1])
            except ValueError:
                return None
        else:
            try:
                return max(self.bgcorrectedtraces2[turn][self.harm2column].iloc[self.maxpeakexclusion:-self.maxpeakexclusion-1] if harmonic == 2 else self.bgcorrectedtraces1[turn][self.harm1column].iloc[self.maxpeakexclusion:-self.maxpeakexclusion-1])
            except ValueError:
                return None

    def get_peaks(self, turn = 0, with_average = True, centerpeak_pos_ns = None, sidepeaks = 0, harmonic = 1):
        """
        Get all peaks, up to ``sidepeaks`` away from the ``centerpeak_pos_ns`` within the ``turn`` window. If ``centerpeak_pos_ns`` is None, provides only the highest peak within the window. 

        Parameters
        ----------
        turn : int, optional
            index of the turn where to obtain peaks. The default is 0.
        with_average : bool, optional
            If True, also get peaks from the averaged traces (have to be generated by calling "do_averaging"). The default is True.
        centerpeak_pos_ns : float, optional
            estimated position of the central peak in nanoseconds relative to the window start. If None, only provide the highest peak within the window. The default is None.
        sidepeaks : int, optional
            number of peaks to be obtained on both sides from the central peak. The default is 0.
        harmonic : int, optional
            Number of harmonic (1,2,...). The default is 1.

        Returns
        -------
        dict
            dictionary containing all peaks with columns of the form 'harmH_turnM_peakN[_avg]' for the given turn M, harmonic H and N from -``sidepeaks`` to ``sidepeaks``

        """
        # centerpeak_pos_ns is time relative to windowstart!!
        datacolumn = self.harm2column if harmonic == 2 else self.harm1column
        
        bgcorrectedtrace = self.get_bg_corrected_trace(turn, harmonic)
        bgavgtrace       = self.get_averaged_bg_corrected_trace(turn, harmonic)
        
        maximadf = dict()
        if centerpeak_pos_ns is None:
            maximum = self.get_max_peak(turn, harmonic=harmonic)
            maximadf.update({f'harm{harmonic}_turn{turn}_peak0': maximum})
            if with_average:
                maximum_avg = self.get_max_peak(turn, average=True, harmonic=harmonic)
                maximadf.update({f'harm{harmonic}_turn{turn}_peak0_avg': maximum_avg})
            return maximadf
        
        windowstart, windowend = self.get_window(turn)
        centerpeak_pos_turn = windowstart + self.time_to_points(centerpeak_pos_ns)
        centerpeak_start = centerpeak_pos_turn - self.bunch_gap_points(0.5)
        centerpeak_end   = centerpeak_pos_turn + self.bunch_gap_points(0.5)
        try:
            centerpeak_max = max(bgcorrectedtrace[datacolumn].loc[centerpeak_start:centerpeak_end-1])
        except ValueError:
            centerpeak_max = None
        maximadf.update({f'harm{harmonic}_turn{turn}_peak0': centerpeak_max})
        if with_average:
            try:
                centerpeak_max_avg = max(bgavgtrace[datacolumn].loc[centerpeak_start:centerpeak_end-1])
            except ValueError:
                centerpeak_max_avg = None
            maximadf.update({f'harm{harmonic}_turn{turn}_peak0_avg': centerpeak_max_avg})
        
        peak_left_start = peak_right_start = centerpeak_start
        peak_left_end   = peak_right_end   = centerpeak_end        
        for i in range(sidepeaks):
            peak_left_end    = peak_left_start
            peak_left_start -= self.bunch_gap_points(1)
            peak_right_start = peak_right_end
            peak_right_end  += self.bunch_gap_points(1)
            
            try:
                peak_left_max  = max(bgcorrectedtrace[datacolumn].loc[peak_left_start:peak_left_end-1])
            except ValueError: # this means the current side peak position is completely outside the bgtrace window
                peak_left_max  = None #issue a warning?
            try:
                peak_right_max = max(bgcorrectedtrace[datacolumn].loc[peak_right_start:peak_right_end-1])
            except ValueError:
                peak_right_max = None #issue a warning?
            maximadf.update({f'harm{harmonic}_turn{turn}_peak{i+1}': peak_right_max})
            maximadf.update({f'harm{harmonic}_turn{turn}_peak{-(i+1)}': peak_left_max})
            if with_average:
                try:
                    peak_left_max_avg  = max(bgavgtrace[datacolumn].loc[peak_left_start:peak_left_end-1])
                except ValueError:
                    peak_left_max_avg  = None #issue a warning?
                try:
                    peak_right_max_avg = max(bgavgtrace[datacolumn].loc[peak_right_start:peak_right_end-1])
                except ValueError:
                    peak_right_max_avg = None #issue a warning?
                maximadf.update({f'harm{harmonic}_turn{turn}_peak{i+1}_avg': peak_right_max_avg})
                maximadf.update({f'harm{harmonic}_turn{turn}_peak{-(i+1)}_avg': peak_left_max_avg})
        
        return maximadf
    
