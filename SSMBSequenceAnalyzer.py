# -*- coding: utf-8 -*-
"""
Created on Mon Jul 19 11:45:00 2021

@author: Arnold Kruschinski
"""

import pandas as pd
from datetime import datetime,timedelta
from copy import deepcopy
from matplotlib import pyplot as plt

from SSMBTraceAnalyzer import TraceAnalyzer
import SSMBTraceAnalyzerUtilities as util


class SequenceAnalyzer:
    
    def __init__(self, filtering:bool = True, filterwidth:int = 2, bgfitorder:int = 2, averaginglength:int = 10, maxturns:int = 9, sidepeaks:int = 2,
                 windowcenter:float = 0., windowwidth:float = 20., centerpeak_pos:str = 'automatic', harm_for_auto_centerpeak:int = 1, turn_for_auto_centerpeak:int = 1,
                 plot:bool = False, plotmax:int = 20, plot_all_chunks:bool = True, plotfolder:str = 'Testplots/',
                 timecolumn_name:str = "TIME", harm1column_name:str = "CH3", harm2column_name:str = "CH4", lasercolumn_name:str = "CH1",
                 invertharm1:bool = False, invertharm2:bool = False, invertlaser:bool = False, laser_threshold:float = 0.03, chunk_gap:int = 5):
        #centerpeak_pos can be 
        #float for manual postitioning NOT at the window center (time in nanoseconds relative to window START)
        #or str:
        #       'automatic': continuosly find center peak within window (default, also set for other str values)
        #       'fixed': automatically find center peak once and keep it fixed
        #       'center': Take the window center position
        #
        # chunk_gap: time delay in seconds between measurements that is allowed for the same data set before starting a new chunk
        
        self.filterwidth = 2
        self.set_filtering(filtering, filterwidth)
        self.set_bg_fit_order(bgfitorder)
        self.set_averaging_length(averaginglength)
        self.set_max_turns(maxturns)
        self.set_sidepeaks(sidepeaks)
        self.windowcenter = windowcenter
        self.windowwidth = windowwidth
                 
        self.centerpeak_pos = None
        self.centerpeak_determination_automatic  = True
        self.centerpeak_determination_continuous = True
        self.harm_for_centerpeak = 1
        self.turn_for_centerpeak = 1
        self.set_centerpeak_pos(centerpeak_pos, harm_for_auto_centerpeak, turn_for_auto_centerpeak)
        
        self.recent_peakdata = {}
        self.reset_sequence()
        self.prev_horizontal_info = (0,0,0)
        self.prev_datetime = datetime(1970,1,1)
        self.chunk_index = -1 # should start with zero, but will be incremented for the first data trace as the time comparison will fail
        
        self.plot = plot
        self.plotmax = plotmax
        self.plot_all_chunks = plot_all_chunks
        self.plotfolder = plotfolder
        if self.plotfolder[-1] != '/':
            self.plotfolder += '/'
        self.plot_index = 0
                
        self.timecolumn = timecolumn_name
        self.harm1column = harm1column_name
        self.harm2column = harm2column_name
        self.lasercolumn = lasercolumn_name
        self.invertharm1 = invertharm1
        self.invertharm2 = invertharm2
        self.invertlaser = invertlaser
        self.laserthreshold = laser_threshold
        self.time_tolerance = chunk_gap
        
        
    def set_averaging_length(self, averaginglength):
        self.averaginglength = averaginglength
        
    def set_filtering(self, filtering, filterwidth=None):
        self.filtering = filtering
        if filterwidth is not None:
            self.filterwidth = filterwidth
        
    def set_bg_fit_order(self, bgfitorder):
        self.fitorder = bgfitorder
        
    #def set_max_harmonic(self, maxharmonic):
        #self.maxharmonic = maxharmonic
    
    def set_max_turns(self, maxturns):
        self.maxturns = maxturns
    
    def set_sidepeaks(self, sidepeaks):
        self.sidepeaks = sidepeaks
    
    def set_window(self, windowcenter, windowwidth):
        if windowcenter != self.windowcenter or windowwidth != self.windowwidth:
            # only do something on changed values
            self.windowcenter = windowcenter
            self.windowwidth = windowwidth
            self.averagecache = ([],[])
            self.peakcache = ([],[])
            # we have to reset averaging and fluctuation calculation as the previous data does not fit anymore due to the changed window
    
    def set_centerpeak_pos(self, centerpeak_pos, harm_for_auto_centerpeak = None, turn_for_auto_centerpeak = None):
        """
        Set the position of the center peak or its determination mode

        Parameters
        ----------
        centerpeak_pos : str or float
            Can be 'automatic' for continuous, automatic centerpeak determination
            Can be 'fixed' to keep the last set centerpeak position fixed. If no position has been set or determined yet, do automatic determination once and keep position fixed afterwards.
            Can be 'center' to manually specify the window center position, and keep it fixed.
            Any other str value or other data type will quietly keep the previous settings.
            Can be a float, time (ns) relative to the peak window *start* for manual centerpeak position input (will stay fixed)            
        harm_for_auto_centerpeak: int
            Number of the harmonic (1 or 2) used for the automatic centerpeak position determination, if active. Default is None (keep unchanged).
        turn_for_auto_centerpeak: int
            Number of the turn used for the automatic centerpeak position determination, if active. Starting with 1 for the first turn after the trigger. Default is None (keep unchanged).

        Returns
        -------
        None.

        """
        if type(centerpeak_pos) == str:
            if centerpeak_pos == 'automatic':
                self.centerpeak_determination_automatic  = True
                self.centerpeak_determination_continuous = True
            elif centerpeak_pos == 'fixed':
                self.centerpeak_determination_automatic  = True
                self.centerpeak_determination_continuous = False
            elif centerpeak_pos == 'center':
                self.centerpeak_pos = self.windowwidth/2
                self.centerpeak_determination_automatic  = False
                self.centerpeak_determination_continuous = False
            else:
                try:
                    self.centerpeak_pos = float(centerpeak_pos) # also accept numerical value given as string (this might happen for automatic type casting in calling classes as the default is string)
                    self.centerpeak_determination_automatic  = False
                    self.centerpeak_determination_continuous = False
                except ValueError:
                    pass # ignore invalid value
        else:
            self.centerpeak_pos = centerpeak_pos
            self.centerpeak_determination_automatic  = False
            self.centerpeak_determination_continuous = False
            
        if turn_for_auto_centerpeak is not None:
            self.turn_for_centerpeak = turn_for_auto_centerpeak -1
        if harm_for_auto_centerpeak is not None:
            self.harm_for_centerpeak = harm_for_auto_centerpeak
    
    def get_centerpeak_pos(self):
        return self.centerpeak_pos
    
    def get_parameters(self):
        """
        returns a dictionary of the current parameter set of the SSMBSequenceAnalyzer
        """
        if self.centerpeak_determination_continuous:
            centerpeak_pos = 'automatic'
        elif self.centerpeak_determination_automatic:
            centerpeak_pos = 'fixed'
        else:
            centerpeak_pos = self.centerpeak_pos
            
        return dict(filtering = self.filtering, filterwidth = self.filterwidth, bgfitorder = self.fitorder, averaginglength = self.averaginglength, maxturns = self.maxturns, sidepeaks = self.sidepeaks,
                 windowcenter = self.windowcenter, windowwidth = self.windowwidth, centerpeak_pos = centerpeak_pos, harm_for_auto_centerpeak = self.harm_for_centerpeak, turn_for_auto_centerpeak = self.turn_for_centerpeak+1,
                 plot = self.plot, plotmax = self.plotmax, plot_all_chunks = self.plot_all_chunks, plotfolder = self.plotfolder,
                 timecolumn_name = self.timecolumn, harm1column_name = self.harm1column, harm2column_name= self.harm2column, lasercolumn_name = self.lasercolumn,
                 invertharm1 = self.invertharm1, invertharm2 = self.invertharm2, invertlaser = self.invertlaser, laser_threshold = self.laserthreshold, chunk_gap = self.time_tolerance)
    
    
    def get_peakdata(self):
        """
        returns the complete DataFrame of logged peakdata from the previous analyes.
        """
        return self.peakdata
    
    def get_peakdata_length(self):
        return len(self.peakdata)

    def get_last_peakdata(self):
        """
        returns the last item in the DataFrame of logged peakdata from the previous analyes
        """
        if len(self.peakdata) > 0:
            return self.peakdata.iloc[-1]

    def get_current_peakdata(self):
        """
        returns the peakdata from the most recent completed analysis, independent of whether logging was on or off
        """
        return self.recent_peakdata
    
    def get_current_trace_analysis(self):
        """
        returns the TraceAnalyzer object from the most recent completed analysis
        """
        return self.recent_trace

    def reset_sequence(self):
        self.chunk_index = 0
        self.averagecache = ([],[])
        self.peakcache = ([],[])
		# define some columns known to exist to fix the order and avoid integer values being converted to float:
        dfcolumns = ['datetime', 'filename', 'chunk_index', 'centerpeak_pos', 'averaging_length_harm1', 'averaging_length_harm2', 'fluctuation_length_harm1', 'fluctuation_length_harm2']
        #self.peakdatacache = pd.DataFrame(columns=dfcolumns)
        #self.peakdata = pd.DataFrame(columns=dfcolumns)
        # there seems to be a bug in old pandas versions that prevents initialization of empty DataFrames with column names only,
        # we have to do it like this:
        dfzeros = pd.DataFrame([[0]*len(dfcolumns)], columns=dfcolumns) # initialize DF with one row of zeros
        self.peakdatacache = dfzeros.drop(0) # drop only row to get empty DF.
        self.peakdata = dfzeros.drop(0)

    def save_peakdata_to_hdf(self, outputfilepath):
        """
        Saves the logged peakdata DataFrame to the file specified by ``outputfilepath`` (should have extension '.hdf5').
        The peakdata is saved under the key 'data', the parameters given to SequenceAnalyzer under the key 'params'. Note that the parameters are as of now not updated to any changes made after initialization of the SequenceAnalyzer object!
        Note that existing data in the file will be overwritten. This can be used to append data, by periodically saving the growing peakdata table, but this is inefficient as all the data is saved every time.
        """
        print(f'saving data to file {outputfilepath}...', end=' ')
        self.peakdata.to_hdf(outputfilepath, key='data', mode='a', complevel=1)
        pd.Series(self.get_parameters()).to_hdf(outputfilepath, key='params', mode='a', complevel=1)
        print('done.')
        
    
############################################################################
    def next_analysis(self, data=None, filepath=None, date_time=None, log_peakdata=True, frf=None):
        """
        do the next file analysis and append the result to peakdata.
        
        Parameters
        ----------
        data : pandas DataFrame, optional
            the scope data to analyze. Default is None (use data from file)
        filepath : str or list of str, optional
            If data=None, path to the file from where to import the tracedata. must be '.csv' of '.wfm'. If list of file paths, must be '.wfm' files to multiple channels of the same measurement. The default is None (use directly provided data).
        date_time : datetime object, optional
            Date/Time of the measurement. Default is None (extract datetime from file or use datetime.now).
        log_peakdata: boolean, optional
            Specifies if the obtained peak data should be logged to the SequenceAnalyzer object's list of peakdata. Default is True.
        frf: float
            Masterclock frequency of the measurement in Hz. Default is None (use 499.7e6 Hz)

        Returns
        -------
        None.
        """
        try:
            currenttrace = TraceAnalyzer(data = data, filepath = filepath, windowwidth_ns=self.windowwidth, windowcenter_ns = self.windowcenter,
                                         frf=frf, timecolumnname=self.timecolumn, harm1columnname = self.harm1column, harm2columnname = self.harm2column, lasercolumnname = self.lasercolumn,
                                         invertharm1 = self.invertharm1, invertharm2 = self.invertharm2, invertlaser = self.invertlaser)
            currenttrace.do_bg_correct(maxturns = self.maxturns, fitorder = self.fitorder, filtering=self.filtering)
        except (RuntimeError, FileNotFoundError) as e:
            print("Skipped dataset at", date_time, filepath)
            print("because:", e)
            return
        
        modtime = None
        if date_time is not None:
            currentdatetime = date_time
        elif filepath is not None:
            if type(filepath) is str:
                currentdatetime = util.extractDatetimeFromDataFilename(filepath)
                modtime = util.extractDatetimeFromDataModtime(filepath)
            else:
                currentdatetime = min(util.extractDatetimeFromDataFilename(f) for f in filepath)
                modtime = min(util.extractDatetimeFromDataModtime(f) for f in filepath)
        else:
            currentdatetime = datetime.now()
        
        if not currenttrace.compare_horizontal_info(*self.prev_horizontal_info) or currentdatetime-self.prev_datetime > timedelta(seconds=self.time_tolerance):
            # reset the averaging, reset the automatic centerpeak position and increment the chunk_index,
            # if either the horizontal scale has changed or the last trace is more than X seconds old
            self.averagecache = ([],[])
            self.peakcache = ([],[])
            if self.centerpeak_determination_automatic:
                self.centerpeak_pos = None # reset the centerpeak_pos to "unknown" only for automatic determination
            self.chunk_index += 1
            if self.plot_all_chunks:
                self.plot_index = 0   # restart plotting
        self.prev_horizontal_info = currenttrace.get_horizontal_info()
        self.prev_datetime = currentdatetime
        
        currenttrace.do_averaging(self.averagecache)
        if len(self.averagecache[self.harm_for_centerpeak-1]) > self.averaginglength-2:    
            if self.centerpeak_pos is None or self.centerpeak_determination_continuous:
                try:
                    bgavgtrace_c = currenttrace.get_averaged_bg_corrected_trace(self.turn_for_centerpeak, harmonic=self.harm_for_centerpeak)
                    centerpeakmax = currenttrace.get_max_peak(self.turn_for_centerpeak, average=True, harmonic=self.harm_for_centerpeak)
                    centerpeakmaxpos = bgavgtrace_c.index[bgavgtrace_c[self.harm2column if self.harm_for_centerpeak==2 else self.harm1column] == centerpeakmax][0]
                    self.centerpeak_pos = currenttrace.points_to_time(centerpeakmaxpos - currenttrace.get_window(self.turn_for_centerpeak)[0])
                except IndexError: # this happens if no data is availible for self.turn_for_centerpeak
                    print("Warning: Automatic centerpeak determination failed: No data for specified turn")
                except TypeError: # this happens if there are no bgavgtraces available at all either if there is no data for the column or bg correction or averaging have not been performed yet
                    print("Warning: Automatic centerpeak determination failed: No data for specified harmonic")

        if filepath is not None:
            if type(filepath) is str:
                filename = filepath.split('/')[-1]
            else:
                filename = ';'.join(sorted([f.split('/')[-1] for f in filepath], key = util.extractChannelNameFromDataFilename))
        else:
            filename = 'direct data transfer'
            
        lasermax, laserpos = currenttrace.get_laser_maximum(self.laserthreshold)
        md = dict(datetime=currentdatetime, filename=filename, chunk_index=self.chunk_index, centerpeak_pos = self.centerpeak_pos, laser_maximum=lasermax, laser_position=laserpos)
        if modtime is not None:
            md.update({'modtime': modtime})
        
        #for h in range(1,maxharmonic+1):
        for h in range(1,3):
            
            if not currenttrace.harmonic_exists(h):
                print(f"Warning: No data columns matching harmonic {h} column names")
                self.averagecache[h-1].clear() # if there is no data for the current column in this trace:
                self.peakcache[h-1].clear()    # reset averaging (delete averagecache) and fluctuation (delete peakcache) as continuity to previous traces is lost when data resumes
                continue # skip to next harmonic
            
            datacolumn = self.harm2column if h == 2 else self.harm1column
            
            bgtraces = []
            #peak0list = []
            
            md.update({f'averaging_length_harm{h}': len(self.averagecache[h-1])+1})
            md.update({f'fluctuation_length_harm{h}': len(self.peakdatacache)+1})
            
            if self.plot and self.plot_index < self.plotmax:
                fig = plt.figure(figsize=(18,9))    
            for t in range(self.maxturns):
                if self.plot and self.plot_index < self.plotmax:
                    plt3 = fig.add_subplot(3, self.maxturns, t+1)
                    plt1 = fig.add_subplot(3, self.maxturns, t+1+self.maxturns)
                    plt2 = fig.add_subplot(3, self.maxturns, t+1+2*self.maxturns)
                try:
                    bgtrace = currenttrace.get_bg_corrected_trace(t, h)
                except IndexError: # this happens when bg fit failed for this turn (probably due to insufficient data, i.e. time axis not extenting far enough)
                    continue       # ==> skip this turn
                bgtraces.append(bgtrace)
                
                if self.centerpeak_pos is not None: #then we can do the bunch-by-bunch get_peaks and averaging.                    
                    md.update(currenttrace.get_peaks(t, with_average=True, centerpeak_pos_ns = self.centerpeak_pos, sidepeaks = self.sidepeaks, harmonic = h))
                    bgavgtrace = currenttrace.get_averaged_bg_corrected_trace(t, h)
                    self.peakdatacache = pd.concat([self.peakdatacache, pd.DataFrame(md, index=[0])], ignore_index = True, sort=True)
                    if len(self.peakdatacache) > self.averaginglength:
                        self.peakdatacache = self.peakdatacache.drop(index=0)
                    #peak0 = md[f'harm{h}_turn{t}_peak0']
                    #peak0list.append(peak0)
                    for p in range(-self.sidepeaks, self.sidepeaks+1):
                        try:
                            md.update({f'harm{h}_turn{t}_peak{p}_std': self.peakdatacache[f'harm{h}_turn{t}_peak{p}'].std(ddof=1)})
                        except KeyError:
                            pass # this happens when the data column is not present, skip fluctuation calculation.
                    #if len(self.peakcache[h-1]) > 0:
                        #cachepeaks = []
                        #for c in self.peakcache[h-1]:
                            #try:
                                #cachepeaks.append(c[t])
                            #except IndexError:
                                #pass # ignore missing data in cache, just use less measurements for fluctuation calculation.
                        #cachepeaks.append(peak0)
                        #try:
                            #md.update({f'harm{h}_turn{t}_fluctuation': np.std(cachepeaks, ddof=1)})
                        #except TypeError:
                            #pass # this happens when np.std fails due to insufficient data (Nones in cachepeak), skip fluctuation calculation for this turn.
                    
                    if self.plot and self.plot_index < self.plotmax:
                        windowstarttime, windowendtime = currenttrace.get_window_times(t)
                        
                        plt1.plot([windowstarttime, windowendtime], [md[f'harm{h}_turn{t}_peak0']]*2, 'm--')
                        for j in range(self.sidepeaks):
                            plt1.plot([windowstarttime, windowendtime], [md[f'harm{h}_turn{t}_peak{j+1}']]*2, 'r--')
                            plt1.plot([windowstarttime, windowendtime], [md[f'harm{h}_turn{t}_peak{-j-1}']]*2, 'r--')
                            
                        plt2.plot([windowstarttime, windowendtime], [md[f'harm{h}_turn{t}_peak0_avg']]*2, 'm--')
                        for j in range(self.sidepeaks):
                            plt2.plot([windowstarttime, windowendtime], [md[f'harm{h}_turn{t}_peak{j+1}_avg']]*2, 'r--')
                            plt2.plot([windowstarttime, windowendtime], [md[f'harm{h}_turn{t}_peak{-j-1}_avg']]*2, 'r--')
                        
                if self.plot and self.plot_index < self.plotmax:
                    plt3.plot(currenttrace.trace[self.timecolumn][slice(*currenttrace.get_window(t))]*1e9, currenttrace.trace[datacolumn][slice(*currenttrace.get_window(t))], 'k')
                    plt3.grid()
                    plt3.set_title(f'harm {h}, turn {t+1}, raw')
                
                # always also do get_max_peak within the window, as centerpeak_pos may be unknown
                currentmax = currenttrace.get_max_peak(t, average=False, harmonic=h)
                try:
                    currentmaxpos = bgtrace.index[bgtrace[datacolumn] == currentmax][0]
                except IndexError: # if nothing found (can happen with NaNs), list will be empty
                    currentmaxpos = None
                md.update({f'harm{h}_turn{t}_max_peak': currentmax})

                if self.plot and self.plot_index < self.plotmax:
                    plt1.plot(bgtrace[self.timecolumn]*1e9, bgtrace[datacolumn], 'b')
                    if currentmaxpos is not None:
                        plt1.plot(bgtrace[self.timecolumn][currentmaxpos]*1e9, currentmax, 'rx')
                    plt1.grid()
                    plt1.set_title(f'harm {h}, turn {t+1}, bgcorr')

                #if len(self.averagecache) > self.averaginglength-2: # if we have enough traces in the cache we can also use the averaged trace!
                # > we can always do this, but possibly with reduced averaging length (which is given in the DataFrame)
                currentmaxavg = currenttrace.get_max_peak(t, average=True, harmonic=h)
                bgavgtrace = currenttrace.get_averaged_bg_corrected_trace(t, h)
                try:
                    currentmaxposavg = bgavgtrace.index[bgavgtrace[datacolumn] == currentmaxavg][0]
                except IndexError: # if nothing found (can happen with NaNs), list will be empty
                    currentmaxposavg = None
                md.update({f'harm{h}_turn{t}_max_peak_avg': currentmaxavg})

                if self.plot and self.plot_index < self.plotmax:
                    plt2.plot(bgavgtrace[self.timecolumn]*1e9, bgavgtrace[datacolumn], 'g')
                    if currentmaxposavg is not None:
                        plt2.plot(bgavgtrace[self.timecolumn][currentmaxposavg]*1e9, currentmaxavg, 'rx')
                    plt2.grid()
                    plt2.set_title(f'harm {h}, turn {t+1}, avg')
                
            self.averagecache[h-1].append(bgtraces)
            if len(self.averagecache[h-1]) > self.averaginglength-1:
                del self.averagecache[h-1][0]
                
            #if len(peak0list) > 0:
                #self.peakcache[h-1].append(peak0list)
            #if len(self.peakcache[h-1]) > self.averaginglength-1:
                #del self.peakcache[h-1][0]

            if self.plot and self.plot_index < self.plotmax:
                fig.savefig(self.plotfolder+f'SequenceAnalyzer_harm{h}_chunk{self.chunk_index}_trace{self.plot_index}.png')
                plt.close(fig)
        
        # copy trace object and data to prevent getting changing or incomplete data when reading current_peakdata at a random time
        self.recent_trace = deepcopy(currenttrace)
        self.recent_peakdata = md.copy()
        if log_peakdata:
            self.peakdata = pd.concat([self.peakdata, pd.DataFrame(md, index=[0])], ignore_index = True, sort=True)
        
        self.plot_index += 1
        print(f"dataset #{len(self.peakdata)} at {date_time}, {filename} done")
