# -*- coding: utf-8 -*-
"""
Created on Thu Jun  2 13:49:09 2022

@author: Arnold Kruschinski
"""

#import matplotlib
#matplotlib.use('TkAgg')

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size': 8})

class SSMBPlotting:
    def __init__(self, harm1master, harm2master, figsize_overview=(6,2), figsize_detail=(2,2)):
        harm1o_fig  = plt.figure('harm1o', figsize=figsize_overview, tight_layout=True)
        harm1t1_fig = plt.figure('harm1t1', figsize=figsize_detail, tight_layout=True)
        harm1t2_fig = plt.figure('harm1t2', figsize=figsize_detail, tight_layout=True)
        harm2o_fig  = plt.figure('harm2o', figsize=figsize_overview, tight_layout=True)
        harm2t1_fig = plt.figure('harm2t1', figsize=figsize_detail, tight_layout=True)
        harm2t2_fig = plt.figure('harm2t2', figsize=figsize_detail, tight_layout=True)
        self.__figures_overview = [harm1o_fig, harm2o_fig]
        self.__figures_detail = [[harm1t1_fig, harm1t2_fig],[harm2t1_fig, harm2t2_fig]]
        
        harm1o_canvas  = FigureCanvasTkAgg(harm1o_fig,  master=harm1master).get_tk_widget()
        harm1t1_canvas = FigureCanvasTkAgg(harm1t1_fig, master=harm1master).get_tk_widget()
        harm1t2_canvas = FigureCanvasTkAgg(harm1t2_fig, master=harm1master).get_tk_widget()
        harm2o_canvas  = FigureCanvasTkAgg(harm2o_fig,  master=harm2master).get_tk_widget()
        harm2t1_canvas = FigureCanvasTkAgg(harm2t1_fig, master=harm2master).get_tk_widget()
        harm2t2_canvas = FigureCanvasTkAgg(harm2t2_fig, master=harm2master).get_tk_widget()
        self.__canvases_overview = [harm1o_canvas, harm2o_canvas]
        self.__canvases_detail = [[harm1t1_canvas, harm1t2_canvas],[harm2t1_canvas, harm2t2_canvas]]
        
        self.clear_all()
        
        
    def get_canvas(self, overview=True, harm=1, turn=1):
        """
        return the canvas of the selected plot:
        overview: boolean for overview or detail plot
        harm: number of harmonic (1 or 2)
        turn: number of turn (1 or 2) for first or higher turn, ignored if overview==True
        """
        if overview:
            return self.__canvases_overview[harm-1]
        else:
            return self.__canvases_detail[harm-1][turn-1]
    
    def redraw(self, traceanalyzer, harm1turns=[1,2,3], harm1peaks=[0,0,0], harm2turns=[1,2,3], harm2peaks=[0,0,0], centerpeak_pos=None,
               timecolumn = 'TIME', harm1column = 'CH3', harm2column = 'CH4', triggercolumn = 'CH2', maxturns = 2, plotlenOverview = 5000):
        """
        Redraw all plots with new data.

        Parameters
        ----------
        traceanalyzer : SSMBTraceAnalyzer object
            containing the new SSMB data trace.
        harm1turns : list of ints, optional
            selected turn numbers to be marked in the plots for the first harmonic. The default is [1,2,3].
        harm1peaks : list of ints, optional
            selected peak numbers to be marked in the plots for the first harmonic. The default is [0,0,0].
        harm2turns : list of ints, optional
            selected turn numbers to be marked in the plots for the second harmonic. The default is [1,2,3].
        harm1peaks : list of ints, optional
            selected peak numbers to be marked in the plots for the first harmonic. The default is [0,0,0].
        centerpeak_pos : float, optional
            position of the central peak in the evaluation. The default is None (not plotted).
        timecolumn : str, optional
            name of the time column in the data. The default is 'TIME'.
        harm1column : str, optional
            name of the first harmonic column in the data. The default is 'CH3'.
        harm2column : str, optional
            name of the second harmonic column in the data. The default is 'CH4'.
        triggercolumn : str, optional
            name of the trigger column in the data. The default is 'CH2'.

        Returns
        -------
        None.

        """
        ### Overview plots for first and second harmonic ###
        for fig, fig12, harm, turns, peaks in zip(self.__figures_overview, self.__figures_detail, [1,2], [harm1turns, harm2turns], [harm1peaks, harm2peaks]):
            # first, determine the two lowest selected turns for plotting
            turnset = set(turns)
            turn1 = min(turnset)
            turnset.remove(turn1)
            try:
                turn2 = min(turnset)
            except ValueError:
                turn2 = turn1 + 1
            if turn1 > maxturns:
                turn1 = maxturns
            if turn2 > maxturns:
                turn2 = maxturns
            turn1 -= 1 # go from 1.. to 0..
            turn2 -= 1 
            try:
                plt.figure(fig.number)
                fig.clear()
                ax1 = plt.gca()
                ax2 = plt.twinx()
                
                for tt in range(maxturns):
                    windowstart, windowend = traceanalyzer.get_window_times(tt)
                    ax1.axvspan(windowstart, windowend, color='r', alpha=0.5 if tt == turn1 or tt == turn2 else 0.2)
                    if centerpeak_pos is not None:
                        ax1.axvline(windowstart+centerpeak_pos, color='k')
                
                datalength = len(traceanalyzer.trace)
                skipping = datalength//plotlenOverview
                if skipping < 1:
                    skipping = 1
                #skipping=2
                try:
                    ax2.plot(traceanalyzer.trace[timecolumn].loc[::skipping]*1e9, traceanalyzer.trace[triggercolumn].loc[::skipping], 'grey')
                except KeyError:
                    pass # missing trigger trace, skip it
                ax1.plot(traceanalyzer.trace[timecolumn].loc[::skipping]*1e9, traceanalyzer.trace[harm2column if harm==2 else harm1column].loc[::skipping], 'C2' if harm==2 else 'C0', alpha=0.8)
                ax1.set_zorder(1)
                ax1.patch.set_visible(False)
                ax1.set_ylabel('raw signal / V')
                ax1.set_xlabel('time / ns')
                ax1.grid()
                plt.yticks([])
                fig.canvas.draw()
            except KeyError: #Missing Data, clear graph
                self.clear(True, harm)
        
        ### detail plots for first and second harmonic, first and higher turn ###
            for fig, turn in zip(fig12, [turn1, turn2]):
                try:
                    plt.figure(fig.number)
                    fig.clear()
                    windowstart, windowend = traceanalyzer.get_window_times(turn)
                    if centerpeak_pos is not None:
                        plt.axvline(windowstart+centerpeak_pos, color='k')
                        for peak, peakturn in zip(peaks, turns):
                            if peakturn-1 == turn:
                                plt.axvline(windowstart+centerpeak_pos+peak*2, color='r', ls='--')
                    try:
                        plt.plot(traceanalyzer.get_averaged_bg_corrected_trace(turn, harm)[timecolumn]*1e9, traceanalyzer.get_averaged_bg_corrected_trace(turn, harm)[harm2column if harm==2 else harm1column], 'C3' if harm==2 else 'C1')
                        plt.plot(traceanalyzer.get_bg_corrected_trace(turn, harm)[timecolumn]*1e9, traceanalyzer.get_bg_corrected_trace(turn, harm)[harm2column if harm==2 else harm1column], 'C2' if harm==2 else 'C0', alpha=0.8)
                    except TypeError:
                        # is thrown if no data exists (trying to index None)
                        pass # just don't plot anything
                    plt.ylabel('corrected signal / V')
                    plt.xlabel('time / ns')
                    plt.grid()
                    fig.canvas.draw()
                except KeyError: #Missing Data, clear graph
                    self.clear(False, harm, turn+1)
                
    
    def clear(self, overview, harm, turn=1):
        """
        clear the graph and redraw empty plot with only grid lines:
        overview: boolean for overview or detail plot
        harm: number of harmonic (1 or 2)
        turn: number of turn (1 or 2) for first or higher turn, ignored if overview==True
        """
        if overview:
            fig = self.__figures_overview[harm-1]
            plt.figure(fig.number)
            fig.clear()
            plt.ylabel('raw signal / V')
        else:
            fig = self.__figures_detail[harm-1][turn-1]
            plt.figure(fig.number)
            fig.clear()
            plt.ylabel('corrected signal / V')
        plt.xlabel('time / ns')
        plt.grid()
        fig.canvas.draw()
                    
    def clear_all(self):
        """
        clear all graphs and redraw empty plots with only grid lines
        """
        self.clear(True, 1)
        self.clear(True, 2)
        self.clear(False, 1, 1)
        self.clear(False, 1, 2)
        self.clear(False, 2, 1)
        self.clear(False, 2, 2)
