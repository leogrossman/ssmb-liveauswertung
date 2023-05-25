# -*- coding: utf-8 -*-
"""
Created on Wed May 18 10:32:43 2022

@author: Arnold Kruschinski
"""

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from configparser import ConfigParser
from inspect import signature

import os
import sys
import numpy as np

from queue import Empty

from SSMBEpicsAccess import SSMBEpics
from SSMBScopeControl import SSMBScopeControl
import SSMBLiveAnalyzer
from SSMBLivePlot import SSMBPlotting

boolean = lambda s: s.lower() in ('true', 't', 'yes', 'y')
booleanTrue = lambda s: s.lower() not in ('false', 'f', 'no', 'n')

def multi_callback(*callbacks):
    def multi_call(*args, **kwargs):
        for callback in callbacks:
            callback(*args, **kwargs)
    return multi_call

def int_validate(entry):
    return str.isdecimal(entry) or entry == '' #allows only positive integers!

def float_validate(entry):
    try:
        float(entry)
        return True
    except ValueError:
        return entry in ['', '-', '.', '-.']

def format_volts(value, significant_digits=3):
    if value is not None:
        if np.isfinite(value):
            if abs(value) < 1 and abs(value) >= 1e-4:
                return ('%%.%dg mV' % significant_digits) % (value*1000)
            else:
                return ('%%.%dg V' % significant_digits) % value
    return 'no data'


class SSMBWindow(tk.Frame):
    
    def __init__(self, master=None, testing=False, plotting=True):
        print('This is python version', sys.version)
        if testing:
            print('Starting SSMB Live Evaluation in TESTING mode!')
        else:
            print('Starting SSMB Live Evaluation!')            
            
        self.plotting = plotting
        
        tk.Frame.__init__(self, master)
        self.__loop_index = 0
        self.__testing_mode = testing
        self.__cfg_key = 'TESTING' if testing else 'CURRENT'
        
        ### set default values for data column names, will be set from config file in startup() ###
        self.__column_time = 'TIME'
        self.__column_harm1 = 'CH3'
        self.__column_harm2 = 'CH4'
        self.__column_laser = 'CH1'
        self.__column_trigger = 'CH2'
        
        ### color constants ###
        self.__color_background = 'LightSkyBlue1'
        self.__color_harm1 = 'LightPink1'
        self.__color_harm2 = 'PaleGreen2'
        self.__color_config = 'grey70'
        self.__color_saving = 'navajo white'
        self.__color_btngreen = 'green3'
        self.__color_btnred = 'firebrick2'
        
        ### configure window ###
        self.master = master
        self.master.title('SSMB Live Data Evaluation')
        self.master.configure(bg=self.__color_background)
                
        ### register validation callbacks ###
        self.__int_validate_callback = (self.master.register(int_validate), '%P')
        self.__float_validate_callback = (self.master.register(float_validate), '%P')
        
        print('Building window...')
        
        ### Frames ###
        self.__frame_harm1 = tk.Frame(self.master, width = 600, height=400, bg=self.__color_harm1)
        self.__frame_harm2 = tk.Frame(self.master, width = 600, height=400, bg=self.__color_harm2)
        self.__frame_harm1.grid(row=1, column=0, padx=10, pady=10)
        self.__frame_harm2.grid(row=1, column=1, padx=10, pady=10, columnspan=4)
        
        self.__frame_config = tk.Frame(self.master, width = 600, height=200, bg=self.__color_config)
        self.__frame_saving = tk.Frame(self.master, width = 600, height=200, bg=self.__color_saving)
        self.__frame_config.grid(row=3, column=0, padx=10, pady=10, rowspan=3)
        self.__frame_saving.grid(row=2, column=1, rowspan=2, padx=10, pady=10)
        
        tk.Label(self.__frame_harm1, text='First Harmonic',  relief=tk.RAISED, bd=1, bg=self.__color_harm1, padx=10).grid(row=0, column=0, sticky=tk.W, pady=2)
        tk.Label(self.__frame_harm2, text='Second Harmonic', relief=tk.RAISED, bd=1, bg=self.__color_harm2, padx=10).grid(row=0, column=0, sticky=tk.W, pady=2)
        
        ### Temporary Plotting on/off button ###
        self.__doplottingBtn = tk.Button(self.master, text='Plotting enabled', width=15, command=self.__toggle_plotting)
        if self.plotting:
            self.__doplottingBtn.configure(text = 'Plotting enabled', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        else:
            self.__doplottingBtn.configure(text = 'Plotting disabled', bg=self.__color_btnred, activebackground=self.__color_btnred)
        self.__doplottingBtn.grid(row=2, column=0)
        
        print('Initialize plotting...')
        ### Initialize plotting module and create graphs ###
        self._plt = SSMBPlotting(self.__frame_harm1, self.__frame_harm2, figsize_overview=(6.8,2), figsize_detail=(2.5,2))
        self._plt.get_canvas(overview=True, harm=1).grid(row=2, column=0, columnspan=8, padx=3, pady=3, sticky=tk.W)
        self._plt.get_canvas(overview=False, harm=1, turn=1).grid(row=4, column=0, rowspan=8, padx=3, pady=3)
        self._plt.get_canvas(overview=False, harm=1, turn=2).grid(row=4, column=3, rowspan=8, columnspan=3, padx=3, pady=3)
        self._plt.get_canvas(overview=True, harm=2).grid(row=2, column=0, columnspan=8, padx=3, pady=3, sticky=tk.W)
        self._plt.get_canvas(overview=False, harm=2, turn=1).grid(row=4, column=0, rowspan=8, padx=3, pady=3)
        self._plt.get_canvas(overview=False, harm=2, turn=2).grid(row=4, column=3, rowspan=8, columnspan=3, padx=3, pady=3)
        print('done.')
        
        tk.Label(self.__frame_harm1, text='raw oscilloscope trace',  relief=tk.RAISED, bd=1, bg='white', padx=10).grid(row=1, column=0, sticky=tk.W)
        tk.Label(self.__frame_harm1, text='first turn, background corrected',  relief=tk.RAISED, bd=1, bg='white', padx=10).grid(row=3, column=0, sticky=tk.W)
        tk.Label(self.__frame_harm1, text='higher turn, background corrected',  relief=tk.RAISED, bd=1, bg='white', padx=10).grid(row=3, column=3, columnspan=3, sticky=tk.W)
        tk.Label(self.__frame_harm2, text='raw oscilloscope trace',  relief=tk.RAISED, bd=1, bg='white', padx=10).grid(row=1, column=0, sticky=tk.W)
        tk.Label(self.__frame_harm2, text='first turn, background corrected',  relief=tk.RAISED, bd=1, bg='white', padx=10).grid(row=3, column=0, sticky=tk.W)
        tk.Label(self.__frame_harm2, text='higher turn, background corrected',  relief=tk.RAISED, bd=1, bg='white', padx=10).grid(row=3, column=3, columnspan=3, sticky=tk.W)
        
        ### Scope scale buttons ###
        self.__harm1autoscale = False
        tk.Label(self.__frame_harm1, text='Scope: Vertical Scale', bg=self.__color_harm1).grid(row=0, column=0, columnspan=3, rowspan=2, sticky=tk.E)
        self.__harm1autoscaleBtn = tk.Button(self.__frame_harm1, text='Manual', width=8, command=self.__scale_harm1_auto)
        self.__harm1autoscaleBtn.grid(row=0, column=3, rowspan=2)
        self.__harm1scaleupBtn = tk.Button(self.__frame_harm1, text='larger', width=5, command=self.__scale_harm1_inc)
        self.__harm1scaleupBtn.grid(row=0, column=4, rowspan=2)
        self.__harm1scaledownBtn = tk.Button(self.__frame_harm1, text='smaller', width=5, command=self.__scale_harm1_dec)
        self.__harm1scaledownBtn.grid(row=0, column=5, rowspan=2)
        
        self.__harm2autoscale = False
        tk.Label(self.__frame_harm2, text='Scope: Vertical Scale', bg=self.__color_harm2).grid(row=0, column=0, columnspan=3, rowspan=2, sticky=tk.E)
        self.__harm2autoscaleBtn = tk.Button(self.__frame_harm2, text='Manual', width=8, command=self.__scale_harm2_auto)
        self.__harm2autoscaleBtn.grid(row=0, column=3, rowspan=2)
        self.__harm2scaleupBtn = tk.Button(self.__frame_harm2, text='larger', width=5, command=self.__scale_harm2_inc)
        self.__harm2scaleupBtn.grid(row=0, column=4, rowspan=2)
        self.__harm2scaledownBtn = tk.Button(self.__frame_harm2, text='smaller', width=5, command=self.__scale_harm2_dec)
        self.__harm2scaledownBtn.grid(row=0, column=5, rowspan=2)
        
        ### Turn and peak selection boxes for first harmonic ###
        tk.Label(self.__frame_harm1, text='peak marker #1', bg=self.__color_harm1, relief=tk.GROOVE).grid(row=3, column=1, columnspan=2)
        self.__harm1t1_peak = tk.IntVar(self.master, value=0)
        self.__harm1t1_peakBox = ttk.Combobox(self.__frame_harm1, textvariable = self.__harm1t1_peak, values=[-1,0,1], state='readonly', width=4)
        self.__harm1t1_peakBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm1t1_peakBox.grid(row=5, column=2)
        tk.Label(self.__frame_harm1, text='peak #', bg=self.__color_harm1).grid(row=5, column=1, sticky=tk.E)
        
        self.__harm1t1_turn = tk.IntVar(self.master, value=1)
        self.__harm1t1_turnBox = ttk.Combobox(self.__frame_harm1, textvariable = self.__harm1t1_turn, values=[1,2,3], state='readonly', width=4)
        self.__harm1t1_turnBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm1t1_turnBox.grid(row=4, column=2)
        tk.Label(self.__frame_harm1, text='turn #', bg=self.__color_harm1).grid(row=4, column=1, sticky=tk.E)
        
        tk.Label(self.__frame_harm1, text='peak marker #2', bg=self.__color_harm1, relief=tk.GROOVE).grid(row=3, column=6, columnspan=2)
        self.__harm1t2_peak = tk.IntVar(self.master, value=0)
        self.__harm1t2_peakBox = ttk.Combobox(self.__frame_harm1, textvariable = self.__harm1t2_peak, values=[-1,0,1], state='readonly', width=4)
        self.__harm1t2_peakBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm1t2_peakBox.grid(row=5, column=7)
        tk.Label(self.__frame_harm1, text='peak #', bg=self.__color_harm1).grid(row=5, column=6, sticky=tk.E)
        
        self.__harm1t2_turn = tk.IntVar(self.master, value=2)
        self.__harm1t2_turnBox = ttk.Combobox(self.__frame_harm1, textvariable = self.__harm1t2_turn, values=[1,2,3], state='readonly', width=4)
        self.__harm1t2_turnBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm1t2_turnBox.grid(row=4, column=7)
        tk.Label(self.__frame_harm1, text='turn #', bg=self.__color_harm1).grid(row=4, column=6, sticky=tk.E)
        
        tk.Label(self.__frame_harm1, text='peak marker #3', bg=self.__color_harm1, relief=tk.GROOVE).grid(row=3, column=8, columnspan=2)
        self.__harm1t3_peak = tk.IntVar(self.master, value=1)
        self.__harm1t3_peakBox = ttk.Combobox(self.__frame_harm1, textvariable = self.__harm1t3_peak, values=[-1,0,1], state='readonly', width=4)
        self.__harm1t3_peakBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm1t3_peakBox.grid(row=5, column=9)
        tk.Label(self.__frame_harm1, text='peak #', bg=self.__color_harm1).grid(row=5, column=8, sticky=tk.E)
        
        self.__harm1t3_turn = tk.IntVar(self.master, value=1)
        self.__harm1t3_turnBox = ttk.Combobox(self.__frame_harm1, textvariable = self.__harm1t3_turn, values=[1,2,3], state='readonly', width=4)
        self.__harm1t3_turnBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm1t3_turnBox.grid(row=4, column=9)
        tk.Label(self.__frame_harm1, text='turn #', bg=self.__color_harm1).grid(row=4, column=8, sticky=tk.E)
        
        ### Result display Entries for first harmonic ###
        self.__harm1t1_peakampl = tk.StringVar(self.master, value=0)
        self.__harm1t1_avgampl = tk.StringVar(self.master, value=0)
        self.__harm1t1_fluctuation = tk.StringVar(self.master, value=0)
        
        self.__harm1t1_peakamplEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t1_peakampl, state='readonly', width=11)
        self.__harm1t1_peakamplEtr.grid(row=7, column=1, columnspan=2)
        self.__harm1t1_avgamplEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t1_avgampl, state='readonly', width=11)
        self.__harm1t1_avgamplEtr.grid(row=9, column=1, columnspan=2)
        self.__harm1t1_fluctuationEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t1_fluctuation, state='readonly', width=11)
        self.__harm1t1_fluctuationEtr.grid(row=11, column=1, columnspan=2)
        
        tk.Label(self.__frame_harm1, text='signal height', bg=self.__color_harm1).grid(row=6, column=1, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm1, text='average height', bg=self.__color_harm1).grid(row=8, column=1, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm1, text='rms fluctuation', bg=self.__color_harm1).grid(row=10, column=1, columnspan=2, sticky=tk.S)
        
        self.__harm1t2_peakampl = tk.StringVar(self.master, value=0)
        self.__harm1t2_avgampl = tk.StringVar(self.master, value=0)
        self.__harm1t2_fluctuation = tk.StringVar(self.master, value=0)
                
        self.__harm1t2_peakamplEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t2_peakampl, state='readonly', width=11)
        self.__harm1t2_peakamplEtr.grid(row=7, column=6, columnspan=2)
        self.__harm1t2_avgamplEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t2_avgampl, state='readonly', width=11)
        self.__harm1t2_avgamplEtr.grid(row=9, column=6, columnspan=2)
        self.__harm1t2_fluctuationEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t2_fluctuation, state='readonly', width=11)
        self.__harm1t2_fluctuationEtr.grid(row=11, column=6, columnspan=2)
        
        tk.Label(self.__frame_harm1, text='signal height', bg=self.__color_harm1).grid(row=6, column=6, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm1, text='average height', bg=self.__color_harm1).grid(row=8, column=6, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm1, text='rms fluctuation', bg=self.__color_harm1).grid(row=10, column=6, columnspan=2, sticky=tk.S)
        
        self.__harm1t3_peakampl = tk.StringVar(self.master, value=0)
        self.__harm1t3_avgampl = tk.StringVar(self.master, value=0)
        self.__harm1t3_fluctuation = tk.StringVar(self.master, value=0)
                
        self.__harm1t3_peakamplEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t3_peakampl, state='readonly', width=11)
        self.__harm1t3_peakamplEtr.grid(row=7, column=8, columnspan=2)
        self.__harm1t3_avgamplEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t3_avgampl, state='readonly', width=11)
        self.__harm1t3_avgamplEtr.grid(row=9, column=8, columnspan=2)
        self.__harm1t3_fluctuationEtr = tk.Entry(self.__frame_harm1, textvariable = self.__harm1t3_fluctuation, state='readonly', width=11)
        self.__harm1t3_fluctuationEtr.grid(row=11, column=8, columnspan=2)
        
        tk.Label(self.__frame_harm1, text='signal height', bg=self.__color_harm1).grid(row=6, column=8, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm1, text='average height', bg=self.__color_harm1).grid(row=8, column=8, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm1, text='rms fluctuation', bg=self.__color_harm1).grid(row=10, column=8, columnspan=2, sticky=tk.S)
        
        ### Turn and peak selection boxes for second harmonic ###
        tk.Label(self.__frame_harm2, text='peak marker #1', bg=self.__color_harm2, relief=tk.GROOVE).grid(row=3, column=1, columnspan=2)
        self.__harm2t1_peak = tk.IntVar(self.master, value=0)
        self.__harm2t1_peakBox = ttk.Combobox(self.__frame_harm2, textvariable = self.__harm2t1_peak, values=[-1,0,1], state='readonly', width=4)
        self.__harm2t1_peakBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm2t1_peakBox.grid(row=5, column=2)
        tk.Label(self.__frame_harm2, text='peak #', bg=self.__color_harm2).grid(row=5, column=1, sticky=tk.E)
        
        self.__harm2t1_turn = tk.IntVar(self.master, value=1)
        self.__harm2t1_turnBox = ttk.Combobox(self.__frame_harm2, textvariable = self.__harm2t1_turn, values=[1,2,3], state='readonly', width=4)
        self.__harm2t1_turnBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm2t1_turnBox.grid(row=4, column=2)
        tk.Label(self.__frame_harm2, text='turn #', bg=self.__color_harm2).grid(row=4, column=1, sticky=tk.E)
        
        tk.Label(self.__frame_harm2, text='peak marker #2', bg=self.__color_harm2, relief=tk.GROOVE).grid(row=3, column=6, columnspan=2)
        self.__harm2t2_peak = tk.IntVar(self.master, value=0)
        self.__harm2t2_peakBox = ttk.Combobox(self.__frame_harm2, textvariable = self.__harm2t2_peak, values=[-1,0,1], state='readonly', width=4)
        self.__harm2t2_peakBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm2t2_peakBox.grid(row=5, column=7)
        tk.Label(self.__frame_harm2, text='peak #', bg=self.__color_harm2).grid(row=5, column=6, sticky=tk.E)
        
        self.__harm2t2_turn = tk.IntVar(self.master, value=2)
        self.__harm2t2_turnBox = ttk.Combobox(self.__frame_harm2, textvariable = self.__harm2t2_turn, values=[1,2,3], state='readonly', width=4)
        self.__harm2t2_turnBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm2t2_turnBox.grid(row=4, column=7)
        tk.Label(self.__frame_harm2, text='turn #', bg=self.__color_harm2).grid(row=4, column=6, sticky=tk.E)
        
        tk.Label(self.__frame_harm2, text='peak marker #3', bg=self.__color_harm2, relief=tk.GROOVE).grid(row=3, column=8, columnspan=2)
        self.__harm2t3_peak = tk.IntVar(self.master, value=1)
        self.__harm2t3_peakBox = ttk.Combobox(self.__frame_harm2, textvariable = self.__harm2t3_peak, values=[-1,0,1], state='readonly', width=4)
        self.__harm2t3_peakBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm2t3_peakBox.grid(row=5, column=9)
        tk.Label(self.__frame_harm2, text='peak #', bg=self.__color_harm2).grid(row=5, column=8, sticky=tk.E)
        
        self.__harm2t3_turn = tk.IntVar(self.master, value=1)
        self.__harm2t3_turnBox = ttk.Combobox(self.__frame_harm2, textvariable = self.__harm2t3_turn, values=[1,2,3], state='readonly', width=4)
        self.__harm2t3_turnBox.bind('<<ComboboxSelected>>', self.__update_epics_parameters)
        self.__harm2t3_turnBox.grid(row=4, column=9)
        tk.Label(self.__frame_harm2, text='turn #', bg=self.__color_harm2).grid(row=4, column=8, sticky=tk.E)
        
        ### Result display Entries for second harmonic ###
        self.__harm2t1_peakampl = tk.StringVar(self.master, value=0)
        self.__harm2t1_avgampl = tk.StringVar(self.master, value=0)
        self.__harm2t1_fluctuation = tk.StringVar(self.master, value=0)
                
        self.__harm2t1_peakamplEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t1_peakampl, state='readonly', width=11)
        self.__harm2t1_peakamplEtr.grid(row=7, column=1, columnspan=2)
        self.__harm2t1_avgamplEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t1_avgampl, state='readonly', width=11)
        self.__harm2t1_avgamplEtr.grid(row=9, column=1, columnspan=2)
        self.__harm2t1_fluctuationEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t1_fluctuation, state='readonly', width=11)
        self.__harm2t1_fluctuationEtr.grid(row=11, column=1, columnspan=2)
        
        tk.Label(self.__frame_harm2, text='signal height', bg=self.__color_harm2).grid(row=6, column=1, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm2, text='average height', bg=self.__color_harm2).grid(row=8, column=1, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm2, text='rms fluctuation', bg=self.__color_harm2).grid(row=10, column=1, columnspan=2, sticky=tk.S)
        
        self.__harm2t2_peakampl = tk.StringVar(self.master, value=0)
        self.__harm2t2_avgampl = tk.StringVar(self.master, value=0)
        self.__harm2t2_fluctuation = tk.StringVar(self.master, value=0)
                
        self.__harm2t2_peakamplEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t2_peakampl, state='readonly', width=11)
        self.__harm2t2_peakamplEtr.grid(row=7, column=6, columnspan=2)
        self.__harm2t2_avgamplEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t2_avgampl, state='readonly', width=11)
        self.__harm2t2_avgamplEtr.grid(row=9, column=6, columnspan=2)
        self.__harm2t2_fluctuationEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t2_fluctuation, state='readonly', width=11)
        self.__harm2t2_fluctuationEtr.grid(row=11, column=6, columnspan=2)
                
        tk.Label(self.__frame_harm2, text='signal height', bg=self.__color_harm2).grid(row=6, column=6, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm2, text='average height', bg=self.__color_harm2).grid(row=8, column=6, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm2, text='rms fluctuation', bg=self.__color_harm2).grid(row=10, column=6, columnspan=2, sticky=tk.S)
        
        self.__harm2t3_peakampl = tk.StringVar(self.master, value=0)
        self.__harm2t3_avgampl = tk.StringVar(self.master, value=0)
        self.__harm2t3_fluctuation = tk.StringVar(self.master, value=0)
                
        self.__harm2t3_peakamplEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t3_peakampl, state='readonly', width=11)
        self.__harm2t3_peakamplEtr.grid(row=7, column=8, columnspan=2)
        self.__harm2t3_avgamplEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t3_avgampl, state='readonly', width=11)
        self.__harm2t3_avgamplEtr.grid(row=9, column=8, columnspan=2)
        self.__harm2t3_fluctuationEtr = tk.Entry(self.__frame_harm2, textvariable = self.__harm2t3_fluctuation, state='readonly', width=11)
        self.__harm2t3_fluctuationEtr.grid(row=11, column=8, columnspan=2)
                
        tk.Label(self.__frame_harm2, text='signal height', bg=self.__color_harm2).grid(row=6, column=8, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm2, text='average height', bg=self.__color_harm2).grid(row=8, column=8, columnspan=2, sticky=tk.S)
        tk.Label(self.__frame_harm2, text='rms fluctuation', bg=self.__color_harm2).grid(row=10, column=8, columnspan=2, sticky=tk.S)
        
        
        ### Evaluation configuration panel ###
        self.__config_focus_cache = 0 # storage for value before focus was obtained, to be restored if focus is lost
        self.__config_avlen = tk.IntVar(self.master, value=20)
        self.__config_avlenEtr = tk.Entry(self.__frame_config, width=10 ,textvariable = self.__config_avlen, validate = 'all', validatecommand = self.__int_validate_callback)
        self.__config_avlenEtr.bind('<Return>', multi_callback(self.__config_set_focus_cache, self.__update_averaging))
        self.__config_avlenEtr.bind('<KP_Enter>', multi_callback(self.__config_set_focus_cache, self.__update_averaging))
        self.__config_avlenEtr.bind('<FocusIn>', self.__config_set_focus_cache)
        self.__config_avlenEtr.bind('<FocusOut>', self.__config_retrieve_focus_cache)
        self.__config_avlenEtr.grid(row=1, column=1)
        self.__config_maxrev = tk.IntVar(self.master, value=2)
        self.__config_maxrevEtr = tk.Entry(self.__frame_config, width=10, textvariable = self.__config_maxrev, validate = 'all', validatecommand = self.__int_validate_callback)
        self.__config_maxrevEtr.bind('<Return>', multi_callback(self.__config_set_focus_cache, self.__update_turns))
        self.__config_maxrevEtr.bind('<KP_Enter>', multi_callback(self.__config_set_focus_cache, self.__update_turns))
        self.__config_maxrevEtr.bind('<FocusIn>', self.__config_set_focus_cache)
        self.__config_maxrevEtr.bind('<FocusOut>', self.__config_retrieve_focus_cache)
        self.__config_maxrevEtr.grid(row=2, column=1)
        self.__config_maxpeak = tk.IntVar(self.master, value=1)
        self.__config_maxpeakEtr = tk.Entry(self.__frame_config, width=10, textvariable = self.__config_maxpeak, validate = 'all', validatecommand = self.__int_validate_callback)
        self.__config_maxpeakEtr.bind('<Return>', multi_callback(self.__config_set_focus_cache, self.__update_peaks))
        self.__config_maxpeakEtr.bind('<KP_Enter>', multi_callback(self.__config_set_focus_cache, self.__update_peaks))
        self.__config_maxpeakEtr.bind('<FocusIn>', self.__config_set_focus_cache)
        self.__config_maxpeakEtr.bind('<FocusOut>', self.__config_retrieve_focus_cache)
        self.__config_maxpeakEtr.grid(row=3, column=1)
        self.__config_wincent = tk.DoubleVar(self.master, value=60)
        self.__config_wincentEtr = tk.Entry(self.__frame_config, width=10, textvariable = self.__config_wincent, validate = 'all', validatecommand = self.__float_validate_callback)
        self.__config_wincentEtr.bind('<Return>', multi_callback(self.__config_set_focus_cache, self.__update_window))
        self.__config_wincentEtr.bind('<KP_Enter>', multi_callback(self.__config_set_focus_cache, self.__update_window))
        self.__config_wincentEtr.bind('<FocusIn>', self.__config_set_focus_cache)
        self.__config_wincentEtr.bind('<FocusOut>', self.__config_retrieve_focus_cache)
        self.__config_wincentEtr.grid(row=4, column=1)
        self.__config_winwidth = tk.DoubleVar(self.master, value=30)
        self.__config_winwidthEtr = tk.Entry(self.__frame_config, width=10, textvariable = self.__config_winwidth, validate = 'all', validatecommand = self.__float_validate_callback)
        self.__config_winwidthEtr.bind('<Return>', multi_callback(self.__config_set_focus_cache, self.__update_window))
        self.__config_winwidthEtr.bind('<KP_Enter>', multi_callback(self.__config_set_focus_cache, self.__update_window))
        self.__config_winwidthEtr.bind('<FocusIn>', self.__config_set_focus_cache)
        self.__config_winwidthEtr.bind('<FocusOut>', self.__config_retrieve_focus_cache)
        self.__config_winwidthEtr.grid(row=5, column=1)
        
        tk.Label(self.__frame_config, text='Configuration', bg=self.__color_config, relief=tk.RAISED).grid(row=0, column=0, sticky=tk.W)
        tk.Label(self.__frame_config, text='(press enter after changing a value)', bg=self.__color_config).grid(row=0, column=0, columnspan=4)
        tk.Label(self.__frame_config, text='Averaging length', padx=5, pady=5, bg=self.__color_config).grid(row=1, column=0, sticky=tk.E)
        tk.Label(self.__frame_config, text='Max. number of revolutions', pady=5, bg=self.__color_config).grid(row=2, column=0, sticky=tk.E)
        tk.Label(self.__frame_config, text='Max. number of side peaks', padx=5, pady=5, bg=self.__color_config).grid(row=3, column=0, sticky=tk.E)
        tk.Label(self.__frame_config, text='Window center (ns from trigger)', padx=5, pady=5, bg=self.__color_config).grid(row=4, column=0, sticky=tk.E)
        tk.Label(self.__frame_config, text='Window width (ns)', padx=5, pady=5, bg=self.__color_config).grid(row=5, column=0, sticky=tk.E)
        tk.Label(self.__frame_config, text='Determination of central peak position:', bg=self.__color_config).grid(row=1, column=3, columnspan=3)
        
        tk.Label(self.__frame_config, bg=self.__color_config, width=2).grid(row=2, column=2)
        
        self.__config_centerautoBtn = tk.Button(self.__frame_config, text='Contin. automatic', command=self.__center2auto, width=12, bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        self.__config_centerautoBtn.grid(row=2, column=3)
        self.__config_centerfixBtn = tk.Button(self.__frame_config, text='Fixed automatic', command=self.__center2fix, width=12)
        self.__config_centerfixBtn.grid(row=2, column=4)
        self.__config_centermanuBtn = tk.Button(self.__frame_config, text='Manual', command=self.__center2manu, width=12)
        self.__config_centermanuBtn.grid(row=2, column=5)
        self.__config_centercenterBtn = tk.Button(self.__frame_config, text='set to center', command=self.__center2center, width=12, state='disabled')
        self.__config_centercenterBtn.grid(row=3, column=5)
        self.__color_btndefault = self.__config_centermanuBtn.cget("background")
        
        self.__config_centerposmode = 'automatic'
        self.__config_centerpos = tk.DoubleVar(self.master, value=15)
        self.__config_centerposEtr = tk.Entry(self.__frame_config, width=8, justify='right', textvariable=self.__config_centerpos, validate='all', validatecommand = self.__float_validate_callback, state='readonly')
        self.__config_centerposEtr.bind('<Return>', multi_callback(self.__config_set_focus_cache, self.__update_centerpos))
        self.__config_centerposEtr.bind('<KP_Enter>', multi_callback(self.__config_set_focus_cache, self.__update_centerpos))
        self.__config_centerposEtr.bind('<FocusIn>', self.__config_set_focus_cache)
        self.__config_centerposEtr.bind('<FocusOut>', self.__config_retrieve_focus_cache)
        self.__config_centerposEtr.grid(row=3, column=3, sticky=tk.E, padx=3)
        tk.Label(self.__frame_config, text='ns from window start', bg=self.__color_config).grid(row=3, column=4, padx=5, sticky=tk.W)
        
        ### Oscilloscope control panel ###
        tk.Label(self.__frame_saving, text='Oscilloscope control', bg=self.__color_saving, relief=tk.RAISED).grid(row=1, column=0, sticky=tk.W)
        
        self.__acq_runBtn = tk.Button(self.__frame_saving, text='Acquisition unknown', width=15, command=self.__acq_run)
        self.__acq_runBtn.grid(row=1, column=1, pady=3)
        self.__acq_sequenceBtn = tk.Button(self.__frame_saving, text='Sequence', width=8, command=self.__acq_sequence)
        self.__acq_sequenceBtn.grid(row=1, column=2)
        
        self.__acq_sequencelen = tk.IntVar(self.master, value=10)
        self.__acq_sequencelenEtr = tk.Entry(self.__frame_saving, width=5, textvariable = self.__acq_sequencelen, justify='right', validate = 'all', validatecommand = self.__int_validate_callback)
        self.__acq_sequencelenEtr.grid(row=1, column=4, sticky=tk.W)
        self.__acq_sequencenum = tk.IntVar(self.master, value=10)
        self.__acq_sequencenumEtr = tk.Entry(self.__frame_saving, width=8, textvariable = self.__acq_sequencenum, justify='right', validate = 'all', validatecommand = self.__int_validate_callback, state='readonly')
        self.__acq_sequencenumEtr.grid(row=1, column=6, sticky=tk.W)
        
        tk.Label(self.__frame_saving, text='length', bg=self.__color_saving).grid(row=1, column=3, sticky=tk.E)
        tk.Label(self.__frame_saving, text='Acqusition no.', bg=self.__color_saving).grid(row=1, column=5, sticky=tk.E)        
        
        ### Data saving panel ###
        tk.Label(self.__frame_saving, text='', bg=self.__color_saving, height=1).grid(row=3, column=0)
        
        self.__rawdata_path = tk.StringVar(self.master)
        self.__rawdata_pathEtr = tk.Entry(self.__frame_saving, width=35, textvariable=self.__rawdata_path)
        self.__rawdata_pathEtr.grid(row=5,column=0, columnspan=2, padx=3)
        self.__rawdata_browseBtn = tk.Button(self.__frame_saving, text='Browse...', command=self.__rawdata_browse)
        self.__rawdata_browseBtn.grid(row=5, column=2, padx=3)
        self.__rawdata_name = tk.StringVar(self.master)
        self.__rawdata_nameEtr = tk.Entry(self.__frame_saving, width=22, textvariable=self.__rawdata_name)
        self.__rawdata_nameEtr.grid(row=5, column=3, columnspan=3, padx=3)
        
        #TODO how can we get the info on number of saved files??
        # self.__rawdata_numsaved = tk.IntVar(self.master, value=0)
        # self.__rawdata_numsavedEtr = tk.Entry(self.__frame_saving, width=8, justify='right', textvariable=self.__rawdata_numsaved, state='readonly')
        # self.__rawdata_numsavedEtr.grid(row=5, column=5, padx=3)

        tk.Label(self.__frame_saving, text='Save raw data', bg=self.__color_saving, relief=tk.RAISED).grid(row=4, column=0, sticky=tk.W)        
        tk.Label(self.__frame_saving, text='saved traces', bg=self.__color_saving).grid(row=6, column=6, padx=3, sticky=tk.W)
        tk.Label(self.__frame_saving, text='path to folder', bg=self.__color_saving).grid(row=6, column=0, sticky=tk.W)
        tk.Label(self.__frame_saving, text='file name', bg=self.__color_saving).grid(row=6, column=3, columnspan=2, sticky=tk.W)
        
        self.__rawdata_saveBtn = tk.Button(self.__frame_saving, text='Start', width=8, command=self.__rawdata_save)
        self.__rawdata_saveBtn.grid(row=5, column=6, padx=3)
        
        tk.Label(self.__frame_saving, text='', bg=self.__color_saving, height=1).grid(row=7, column=0)
        
        self.__logging_path = tk.StringVar(self.master)
        self.__logging_pathEtr = tk.Entry(self.__frame_saving, width=35, textvariable=self.__logging_path)
        self.__logging_pathEtr.grid(row=9, column=0, columnspan=2, padx=3)
        self.__logging_browseBtn = tk.Button(self.__frame_saving, text='Browse...', command=self.__logging_browse)
        self.__logging_browseBtn.grid(row=9, column=2, padx=3)
        
        self.__logging_numsaved = tk.IntVar(self.master, value=0)
        self.__logging_numsavedEtr = tk.Entry(self.__frame_saving, width=8, justify='right', textvariable=self.__logging_numsaved, state='readonly')
        self.__logging_numsavedEtr.grid(row=8, column=2, padx=3)

        tk.Label(self.__frame_saving, text='Log evaluation results', bg=self.__color_saving, relief=tk.RAISED).grid(row=8, column=0, sticky=tk.W)        
        tk.Label(self.__frame_saving, text='logged results', bg=self.__color_saving).grid(row=8, column=3, columnspan=2, padx=3, sticky=tk.W)
        tk.Label(self.__frame_saving, text='path to file', bg=self.__color_saving).grid(row=10, column=0, sticky=tk.W)
        #tk.Label(self.__frame_saving, text='file name', bg=self.__color_saving).grid(row=10, column=2, sticky=tk.W)
        
        self.__logging_status = False
        self.__logging_startstopBtn = tk.Button(self.__frame_saving, text='Start', width=8, command=self.__logging_startstop)
        self.__logging_startstopBtn.grid(row=8, column=1, padx=3)
        self.__logging_clearBtn = tk.Button(self.__frame_saving, text='Clear', width=8, command=self.__logging_clear)
        self.__logging_clearBtn.grid(row=8, column=6, sticky=tk.W)
        
        self.__logging_saveBtn = tk.Button(self.__frame_saving, text='Save logged data (disabled)', width=20)#, command=self.__logging_save)
        self.__logging_saveBtn.grid(row=9, column=3, columnspan=3, padx=3, sticky=tk.W)

        ### register window closing protocol ###
        self.master.protocol("WM_DELETE_WINDOW", self.close)
        
        ### open configuration file for reading ###     
        print('Read configuration file...')
        self.__cfg_name = 'SSMBLiveAnalysisConfig.ini'
        self._cfg = ConfigParser()
        self._cfg.read(self.__cfg_name) # TODO config file is only found if python is called from the file directory!
        
        ### read file/path information for data saving from config file ###
        try:
            self.__rawdata_path.set(self._cfg[self.__cfg_key]['savedest'])
        except KeyError:
            print(f'Warning: Cannot recover last known raw data saving directory, key "savedest" does not exist in configuration file "{self.__cfg_name}".')
        
        try:
            self.__scope_mountdir = (self._cfg[self.__cfg_key]['mountdir'])
        except KeyError:
            print(f'Warning: Cannot read network drive mount point for the scope, key "mountdir" does not exist in configuration file "{self.__cfg_name}". Raw data saving functionality is disabled.')
            self.__scope_mountdir = None
        try:
            self.__scope_mountletter = (self._cfg[self.__cfg_key]['mountletter'])
        except KeyError:
            print(f'Warning: Cannot read network drive mount letter for the scope, key "mountletter" does not exist in configuration file "{self.__cfg_name}". Raw data saving functionality is disabled.')
            self.__scope_mountdir = None
            self.__scope_mountletter = None
        try:
            self.__logging_path.set(self._cfg[self.__cfg_key]['logdest'])
        except KeyError:
            print(f'Warning: Cannot recover last known data logging file, key "logdest" does not exist in configuration file "{self.__cfg_name}".')
        print('done.')
        
        ### Initialize EPICS output module ###
        print('Initialize EPICS access...')
        self._epics = SSMBEpics(demo_mode = self.__testing_mode) # if in testing mode, start epics module in demo mode without actual epics access
        print('done.')


    def startup(self):
        ##### read config for scope IP and SequenceAnalyzer init #####
        try:
            scopeip = self._cfg[self.__cfg_key]['scopeip']
        except KeyError:
            print('\nError: IP address for SSMB scope unknown. Check configuration file "%s" for key "scopeip". Exiting.' % self.__cfg_name)
            if self.__testing_mode:
                print('This is testing mode. Continuing anyway.')
            else:
                self.shutdown()
                return
        
        ### read evaluation configuration parameters from config file, parsing datatypes and default values from SequenceAnalyzer annotation ###
        print('Initialize data analysis...')
        parametersignature = signature(SSMBLiveAnalyzer.SequenceAnalyzer)
        parameters = {}
        for parametername in parametersignature.parameters:
            parametertype = parametersignature.parameters[parametername].annotation
            if parametertype is bool:
                parametertype = boolean
            try:
                parameters.update({parametername: parametertype(self._cfg[self.__cfg_key][parametername])})
            except KeyError:
                print('Information: SSMBSequenceAnalyzer parameter "%s" not in configuration file "%s"' % (parametername, self.__cfg_name))
            except ValueError:
                print('Warning: SSMBSequenceAnalyzer parameter "%s" with invalid value in configuration file "%s"' % (parametername, self.__cfg_name))
        ### initialize data analysis module ###
        self._analyzer = SSMBLiveAnalyzer.SSMBLiveAnalyzer(self._epics, self.__logging_status, **parameters)
        print('done.')
        
        ### read initial parameters and update config input elements ###
        # after having written the parameters to the SequenceAnalyzer, now read them back from there to update the front panel elements.
        # this is done because some parameters might be missing in the ini file and are recovered using the defaults in SSMBSequenceAnalyzer.
        setparameters = self._analyzer.get_parameters()
        if type(setparameters['centerpeak_pos']) == str:
            if setparameters['centerpeak_pos'] == 'fixed':
                self.__center2fix(statechange=False)
            else:
                self.__center2auto(statechange=False)
        else:
            self.__center2manu(statechange=False)
            self.__config_centerpos.set(setparameters['centerpeak_pos'])
        self.__config_avlen.set(setparameters['averaginglength'])
        self.__config_maxrev.set(setparameters['maxturns'])
        self.__config_maxpeak.set(setparameters['sidepeaks'])
        self.__config_wincent.set(setparameters['windowcenter'])
        self.__config_winwidth.set(setparameters['windowwidth'])
        
        turnlist = list(range(1,setparameters['maxturns']+1))
        self.__harm1t1_turnBox.configure(values=turnlist)
        self.__harm2t1_turnBox.configure(values=turnlist)
        self.__harm1t2_turnBox.configure(values=turnlist)
        self.__harm2t2_turnBox.configure(values=turnlist)
        self.__harm1t3_turnBox.configure(values=turnlist)
        self.__harm2t3_turnBox.configure(values=turnlist)
        peaklist = list(range(-setparameters['sidepeaks'], setparameters['sidepeaks']+1))
        self.__harm1t1_peakBox.configure(values=peaklist)
        self.__harm2t1_peakBox.configure(values=peaklist)
        self.__harm1t2_peakBox.configure(values=peaklist)
        self.__harm2t2_peakBox.configure(values=peaklist)        
        self.__harm1t3_peakBox.configure(values=peaklist)
        self.__harm2t3_peakBox.configure(values=peaklist)
        
        ### get data column names for plotting ###
        try:
            self.__column_time = self._cfg[self.__cfg_key]['timecolumn_name']
        except KeyError:
            print('Information: Data column name parameter "timecolumn_name" not in configuration file "%s", using default %s' % (self.__cfg_name, self.__column_time))
        try:
            self.__column_harm1 = self._cfg[self.__cfg_key]['harm1column_name']
        except KeyError:
            print('Information: Data column name parameter "harm1column_name" not in configuration file "%s", using default %s' % (self.__cfg_name, self.__column_harm1))
        try:
            self.__column_harm2 = self._cfg[self.__cfg_key]['harm2column_name']
        except KeyError:
            print('Information: Data column name parameter "harm2column_name" not in configuration file "%s", using default %s' % (self.__cfg_name, self.__column_harm2))
        try:
            self.__column_laser = self._cfg[self.__cfg_key]['lasercolumn_name']
        except KeyError:
            print('Information: Data column name parameter "lasercolumn_name" not in configuration file "%s", using default %s' % (self.__cfg_name, self.__column_laser))
        try:
            self.__column_trigger = self._cfg[self.__cfg_key]['trigcolumn_name']
        except KeyError:
            print('Information: Data column name parameter "trigcolumn_name" not in configuration file "%s", using default %s' % (self.__cfg_name, self.__column_trigger))
            
        ### connect to scope ###
        try:
            print(f'Connecting to MSO-64 scope (IP: {scopeip})...') 
            self._ctrl = SSMBScopeControl(scopeip, self._analyzer.data_queue, self._analyzer.maxvalue_queue)
            idn = self._ctrl.get_id()
            print('Connection to SSMB scope successful. Scope ID:')
            print(idn)
            self._ctrl.start()     # start scope control and data acquisition loop
            self._analyzer.start() # start data analysis loop
            self._epics.start()    # start loop for putting evaluation results to EPICS 
            self.loop_run = True
            self.master.after(0, self.main_loop) # start GUI loop
        except Exception as e:
            print('\nError: Connection to SSMB scope failed. Message:\n%s %s\nCheck configuration file "%s" for key "scopeip". Exiting.\n' % (type(e), e, self.__cfg_name))
            if self.__testing_mode:
                print('This is testing mode. Continuing anyway. Control loops have not started.')
            else:
                self.shutdown()
    
    def __config_set_focus_cache(self, event):
		# save the current value of the calling element (to be called at focus in)
        self.__config_focus_cache = event.widget.get()
        
    def __config_retrieve_focus_cache(self, event):
		# reset the value of the calling element to the cached value (to be called at focus out)
        event.widget.delete(0, tk.END)
        event.widget.insert(0, self.__config_focus_cache)
    
    def __update_averaging(self, event):
        self._analyzer.parameter_queue.put(['avglen', self.__config_avlen.get()])
    
    def __update_epics_parameters(self, event=None):
        if self.__testing_mode:
            print('TESTING: changing EPICS parameters...')
        self._epics.set_turn_parameters([self.__harm1t1_turn.get(), self.__harm1t2_turn.get(), self.__harm1t3_turn.get()],
                                        [self.__harm1t1_peak.get(), self.__harm1t2_peak.get(), self.__harm1t3_peak.get()],
                                        [self.__harm2t1_turn.get(), self.__harm2t2_turn.get(), self.__harm2t3_turn.get()],
                                        [self.__harm2t1_peak.get(), self.__harm2t2_peak.get(), self.__harm2t3_peak.get()])
    
    def __update_turns(self, event):
        maxt = self.__config_maxrev.get()
        self._analyzer.parameter_queue.put(['turns', maxt])
        
        turnlist = list(range(1,maxt+1))
        self.__harm1t1_turnBox.configure(values=turnlist)
        if self.__harm1t1_turn.get() > maxt:
            self.__harm1t1_turn.set(maxt)
        self.__harm2t1_turnBox.configure(values=turnlist)
        if self.__harm2t1_turn.get() > maxt:
            self.__harm2t1_turn.set(maxt)
        self.__harm1t2_turnBox.configure(values=turnlist)
        if self.__harm1t2_turn.get() > maxt:
            self.__harm1t2_turn.set(maxt)
        self.__harm2t2_turnBox.configure(values=turnlist)
        if self.__harm2t2_turn.get() > maxt:
            self.__harm2t2_turn.set(maxt)
        self.__harm1t3_turnBox.configure(values=turnlist)
        if self.__harm1t3_turn.get() > maxt:
            self.__harm1t3_turn.set(maxt)
        self.__harm2t3_turnBox.configure(values=turnlist)
        if self.__harm2t3_turn.get() > maxt:
            self.__harm2t3_turn.set(maxt)
        self.__update_epics_parameters()
    
    def __update_peaks(self, event):
        maxp = self.__config_maxpeak.get()
        self._analyzer.parameter_queue.put(['peaks', maxp])
        
        peaklist = list(range(-maxp, maxp+1))
        self.__harm1t1_peakBox.configure(values=peaklist)
        if self.__harm1t1_peak.get() > maxp:
            self.__harm1t1_peak.set(maxp)
        if self.__harm1t1_peak.get() < -maxp:
            self.__harm1t1_peak.set(-maxp)
        self.__harm1t2_peakBox.configure(values=peaklist)
        if self.__harm1t2_peak.get() > maxp:
            self.__harm1t2_peak.set(maxp)
        if self.__harm1t2_peak.get() < -maxp:
            self.__harm1t2_peak.set(-maxp)
        self.__harm2t1_peakBox.configure(values=peaklist)
        if self.__harm2t1_peak.get() > maxp:
            self.__harm2t1_peak.set(maxp)
        if self.__harm2t1_peak.get() < -maxp:
            self.__harm2t1_peak.set(-maxp)
        self.__harm2t2_peakBox.configure(values=peaklist)
        if self.__harm2t2_peak.get() > maxp:
            self.__harm2t2_peak.set(maxp)
        if self.__harm2t2_peak.get() < -maxp:
            self.__harm2t2_peak.set(-maxp)
        self.__update_epics_parameters()
            
    def __update_window(self, event):
        self._analyzer.parameter_queue.put(['window', self.__config_wincent.get(), self.__config_winwidth.get()])
    
    def __update_centerpos(self, event):
        if self.__config_centerposmode == 'manual':
            self._analyzer.parameter_queue.put(['centerpos', self.__config_centerpos.get()])
        else:
            self._analyzer.parameter_queue.put(['centerpos', self.__config_centerposmode])
    
    # TODO Add configuration for turn & peak for auto centerpos determination?       
    def __center2auto(self, statechange = True):
        self.__config_centerposmode = 'automatic'
        self.__config_centerautoBtn.configure(bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        self.__config_centerfixBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self.__config_centermanuBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self.__config_centerposEtr.configure(state='readonly')
        self.__config_centercenterBtn.configure(state='disabled')
        # statechange == False is used to only update the interface, in that case only the mode and buttons are changed.
        if statechange:
            self.__update_centerpos(event=None)
            
    #TODO reset option for fixed auto centerpeak?
    def __center2fix(self, statechange = True):
        self.__config_centerposmode = 'fixed'
        self.__config_centerautoBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self.__config_centerfixBtn.configure(bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        self.__config_centermanuBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self.__config_centerposEtr.configure(state='readonly')
        self.__config_centercenterBtn.configure(state='disabled')
        # statechange == False is used to only update the interface, in that case only the mode and buttons are changed.
        if statechange:
            self.__update_centerpos(event=None)
    
    def __center2manu(self, statechange = True):
        self.__config_centerposmode = 'manual'
        self.__config_centerautoBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self.__config_centerfixBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self.__config_centermanuBtn.configure(bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        self.__config_centerposEtr.configure(state='normal')
        self.__config_centercenterBtn.configure(state='normal')
        # statechange == False is used to only update the interface, in that case only the mode and buttons are changed.
        if statechange:
            self.__update_centerpos(event=None)
    
    def __center2center(self):
        self.__config_centerpos.set(self.__config_winwidth.get()/2)
        self.__update_centerpos(event=None)
    
    def __scale_harm1_auto(self):
        if self.__harm1autoscale:
            self._ctrl.control_queue.put(['manuscale', 0])
            self.__harm1autoscale = False
            self.__harm1autoscaleBtn.configure(text='Manual', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        else:
            self._ctrl.control_queue.put(['autoscale', 0, self.__column_harm1])
            self.__harm1autoscale = True
            self.__harm1autoscaleBtn.configure(text='Automatic', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
    
    def __scale_harm1_inc(self):
        if self.__harm1autoscale:
            self._ctrl.control_queue.put(['manuscale', 0])
            self.__harm1autoscale = False
            self.__harm1autoscaleBtn.configure(text='Manual', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self._ctrl.control_queue.put(['increase', self.__column_harm1])
    
    def __scale_harm1_dec(self):
        if self.__harm1autoscale:
            self._ctrl.control_queue.put(['manuscale', 0])
            self.__harm1autoscale = False
            self.__harm1autoscaleBtn.configure(text='Manual', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self._ctrl.control_queue.put(['decrease', self.__column_harm1])
    
    def __scale_harm2_auto(self):
        if self.__harm2autoscale:
            self._ctrl.control_queue.put(['manuscale', 1])
            self.__harm2autoscale = False
            self.__harm2autoscaleBtn.configure(text='Manual', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        else:
            self._ctrl.control_queue.put(['autoscale', 1, self.__column_harm2])
            self.__harm2autoscale = True
            self.__harm2autoscaleBtn.configure(text='Automatic', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
    
    def __scale_harm2_inc(self):
        if self.__harm2autoscale:
            self._ctrl.control_queue.put(['manuscale', 1])
            self.__harm2autoscale = False
            self.__harm2autoscaleBtn.configure(text='Manual', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self._ctrl.control_queue.put(['increase', self.__column_harm2])
    
    def __scale_harm2_dec(self):
        if self.__harm2autoscale:
            self._ctrl.control_queue.put(['manuscale', 1])
            self.__harm2autoscale = False
            self.__harm2autoscaleBtn.configure(text='Manual', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        self._ctrl.control_queue.put(['decrease', self.__column_harm2])
        
    def main_loop(self):
        while self._ctrl.status_queue.qsize(): # iterate as long as there are status items to get
            self.refresh_acquisition(*self._ctrl.status_queue.get_nowait()) # refresh acquisition display with new status infos
        try:
            newdata = self._analyzer.result_queue.get_nowait() # get newest analyzed data (result_queue is a LIFO queue)
            while self._analyzer.result_queue.qsize():
                self._analyzer.result_queue.get_nowait() # get and discard any older data still in the queue
            self.refresh_display(*newdata) # try to get new analysis result
        except Empty:
            pass # no new data, continue waiting
        if self.loop_run:
            self.master.after(10, self.main_loop) # restart the loop (we cannot wait for new data within a Queue.get() as this would block the GUI thread)
    

    def refresh_acquisition(self, acqstate, acqnumber, savestatus, seqlen = None):
        self.__acq_sequencenum.set(acqnumber)
        self.__acqstate = acqstate
        if acqstate == 'RUN':
            self.__acq_runBtn.configure(text='Acquisition running', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
            self.__acq_sequenceBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        elif acqstate == 'SEQUENCE':
            self.__acq_runBtn.configure(text='Acquisition running', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
            self.__acq_sequenceBtn.configure(bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        elif acqstate == 'STOP':
            self.__acq_runBtn.configure(text='Acquisition stopped', bg=self.__color_btnred, activebackground=self.__color_btnred)
            self.__acq_sequenceBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        else:
            self.__acq_runBtn.configure(text='Acquisition unknown', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
            self.__acq_sequenceBtn.configure(bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        
        self.__savestatus = savestatus
        if savestatus:
            self.__rawdata_saveBtn.configure(text='Stop', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
        else:
            self.__rawdata_saveBtn.configure(text='Start', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
        
        if seqlen is not None:
            self.__acq_sequencelen.set(seqlen)
    
        
    def refresh_display(self, traceanalyzer, peakdata, centerpeakpos, analysislength):
        try:
            self.__harm1t1_peakampl.set(format_volts(peakdata[f'harm1_turn{self.__harm1t1_turn.get()-1}_peak{self.__harm1t1_peak.get()}']))
        except KeyError:
            self.__harm1t1_peakampl.set('no data')
        try:
            self.__harm1t1_avgampl.set(format_volts(peakdata[f'harm1_turn{self.__harm1t1_turn.get()-1}_peak{self.__harm1t1_peak.get()}_avg']))
        except KeyError:
            self.__harm1t1_avgampl.set('no data')
        try:
            self.__harm1t1_fluctuation.set(format_volts(peakdata[f'harm1_turn{self.__harm1t1_turn.get()-1}_peak{self.__harm1t1_peak.get()}_std']))
        except KeyError:
            self.__harm1t1_fluctuation.set('no data')
        
        try:
            self.__harm1t2_peakampl.set(format_volts(peakdata[f'harm1_turn{self.__harm1t2_turn.get()-1}_peak{self.__harm1t2_peak.get()}']))
        except KeyError:
            self.__harm1t2_peakampl.set('no data')        
        try:
            self.__harm1t2_avgampl.set(format_volts(peakdata[f'harm1_turn{self.__harm1t2_turn.get()-1}_peak{self.__harm1t2_peak.get()}_avg']))
        except KeyError:
            self.__harm1t2_avgampl.set('no data')            
        try:
            self.__harm1t2_fluctuation.set(format_volts(peakdata[f'harm1_turn{self.__harm1t2_turn.get()-1}_peak{self.__harm1t2_peak.get()}_std']))
        except KeyError:
            self.__harm1t2_fluctuation.set('no data')
            
        try:
            self.__harm1t3_peakampl.set(format_volts(peakdata[f'harm1_turn{self.__harm1t3_turn.get()-1}_peak{self.__harm1t3_peak.get()}']))
        except KeyError:
            self.__harm1t3_peakampl.set('no data')        
        try:
            self.__harm1t3_avgampl.set(format_volts(peakdata[f'harm1_turn{self.__harm1t3_turn.get()-1}_peak{self.__harm1t3_peak.get()}_avg']))
        except KeyError:
            self.__harm1t3_avgampl.set('no data')            
        try:
            self.__harm1t3_fluctuation.set(format_volts(peakdata[f'harm1_turn{self.__harm1t3_turn.get()-1}_peak{self.__harm1t3_peak.get()}_std']))
        except KeyError:
            self.__harm1t3_fluctuation.set('no data')
        
        
        try:
            self.__harm2t1_peakampl.set(format_volts(peakdata[f'harm2_turn{self.__harm2t1_turn.get()-1}_peak{self.__harm2t1_peak.get()}']))
        except KeyError:
            self.__harm2t1_peakampl.set('no data')
        try:
            self.__harm2t1_avgampl.set(format_volts(peakdata[f'harm2_turn{self.__harm2t1_turn.get()-1}_peak{self.__harm2t1_peak.get()}_avg']))
        except KeyError:
            self.__harm2t1_avgampl.set('no data')
        try:
            self.__harm2t1_fluctuation.set(format_volts(peakdata[f'harm2_turn{self.__harm2t1_turn.get()-1}_peak{self.__harm2t1_peak.get()}_std']))
        except KeyError:
            self.__harm2t1_fluctuation.set('no data')
        
        try:
            self.__harm2t2_peakampl.set(format_volts(peakdata[f'harm2_turn{self.__harm2t2_turn.get()-1}_peak{self.__harm2t2_peak.get()}']))
        except KeyError:
            self.__harm2t2_peakampl.set('no data')
        try:
            self.__harm2t2_avgampl.set(format_volts(peakdata[f'harm2_turn{self.__harm2t2_turn.get()-1}_peak{self.__harm2t2_peak.get()}_avg']))
        except KeyError:
            self.__harm2t2_avgampl.set('no data')
        try:
            self.__harm2t2_fluctuation.set(format_volts(peakdata[f'harm2_turn{self.__harm2t2_turn.get()-1}_peak{self.__harm2t2_peak.get()}_std']))
        except KeyError:
            self.__harm2t2_fluctuation.set('no data')
            
        try:
            self.__harm2t3_peakampl.set(format_volts(peakdata[f'harm2_turn{self.__harm2t3_turn.get()-1}_peak{self.__harm2t3_peak.get()}']))
        except KeyError:
            self.__harm2t3_peakampl.set('no data')
        try:
            self.__harm2t3_avgampl.set(format_volts(peakdata[f'harm2_turn{self.__harm2t3_turn.get()-1}_peak{self.__harm2t3_peak.get()}_avg']))
        except KeyError:
            self.__harm2t3_avgampl.set('no data')
        try:
            self.__harm2t3_fluctuation.set(format_volts(peakdata[f'harm2_turn{self.__harm2t3_turn.get()-1}_peak{self.__harm2t3_peak.get()}_std']))
        except KeyError:
            self.__harm2t3_fluctuation.set('no data')
        
        
        if self.__config_centerposmode != 'manual':
            if centerpeakpos is None:
                self.__config_centerpos.set('unknown')
            else:
                self.__config_centerpos.set('%.1f' % centerpeakpos)
        self.__logging_numsaved.set(analysislength)
        if self.plotting:
            self._plt.redraw(traceanalyzer,
                            [self.__harm1t1_turn.get(), self.__harm1t2_turn.get(), self.__harm1t3_turn.get()],
                            [self.__harm1t1_peak.get(), self.__harm1t2_peak.get(), self.__harm1t3_peak.get()],
                            [self.__harm2t1_turn.get(), self.__harm2t2_turn.get(), self.__harm2t3_turn.get()],
                            [self.__harm2t1_peak.get(), self.__harm2t2_peak.get(), self.__harm2t3_peak.get()],
                            centerpeakpos, maxturns=self.__config_maxrev.get(),
                            timecolumn=self.__column_time, harm1column=self.__column_harm1, harm2column=self.__column_harm2, triggercolumn=self.__column_trigger)
	
    def __toggle_plotting(self):
        if self.plotting:
            self.plotting = False
            self.__doplottingBtn.configure(text = 'Plotting disabled', bg=self.__color_btnred, activebackground=self.__color_btnred)
        else:
            self.plotting = True
            self.__doplottingBtn.configure(text = 'Plotting enabled', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
			

    def __acq_run(self):
        try:
            if self.__acqstate == 'STOP':
                self._ctrl.control_queue.put(['start'])
            else:
                self._ctrl.control_queue.put(['stop'])
        except AttributeError:
            print('Warning: Tried to start/stop acquisition, but the program backend has not started!')
    
    def __acq_sequence(self):
        seqlen = self.__acq_sequencelen.get()
        try:
            if seqlen > 0:
                self._ctrl.control_queue.put(['sequence', seqlen])
            else:
                self._ctrl.control_queue.put(['sequence'])
        except AttributeError:
            print('Warning: Tried to start/stop acquisition, but the program backend has not started!')
        
    def __rawdata_browse(self):
        browsed = filedialog.askdirectory(parent=self.master, title="Choose a directory for saving raw scope traces", initialdir=self.__rawdata_path.get())
        if type(browsed) is str:
            if len(browsed) > 0:
                self.__rawdata_path.set(browsed)
        
    def __rawdata_save(self):
        if self.__scope_mountdir is None:
            print("Error: Cannot start saving data, the scope's network drive mounting point is unknown. Check configuration file.")
            return
        try:
            if self.__savestatus: #TODO is now using last known status, might have changed...
                self._ctrl.control_queue.put(['savestop']) # if saving is running, stop it now
            else: ### start saving ### first: build path
                absdir = self.__rawdata_path.get() # get absolute path that has been input
                reldir = os.path.relpath(absdir, start=self.__scope_mountdir) # get relative path from scope network drive mount point to entered path
                if reldir.startswith('..'): # this means entered path is above mounting point, cannot be accessed from the scope
                    print("Error: Cannot start saving data, given path is not below the scope's network drive mounting point.")
                    tk.messagebox.showerror("Cannot start saving data", f"Cannot start saving raw scope data, the given path is not relative to the scope's network drive mounting point, which is {self.__scope_mountdir}.")
                    return
                if os.path.exists(absdir) and not os.path.isdir(absdir): # path points to an existing file, not folder
                    tk.messagebox.showerror("Please enter directory", 'Please enter a directory in the field "path to folder", a file was given.')
                    return
                if not os.path.isdir(absdir): # if directory does not exist, prompt to create it or cancel
                    if tk.messagebox.askokcancel('Proceed to create directory?', 'The given directory in the field "path to folder" does not exist, create it now?'):
                        os.makedirs(absdir)
                    else:
                        return
                savedir = self.__scope_mountletter + ':/' + reldir # build absolute path from scope's point of view (mount letter + colon + slash + relative path from mounting point)
                #TODO catch illegal file names?
                print('start data saving at', absdir)
                self._ctrl.control_queue.put(['savestart', savedir, self.__rawdata_name.get()]) # start saving data in this directory with entered filename pattern
        except AttributeError: # catch nonexisting scope control
            print('Warning: Tried to start/stop raw data saving, but the program backend has not started!')
    
    def __logging_startstop(self):
        if self.__logging_status:
            self.__logging_status = False
            self.__logging_startstopBtn.configure(text = 'Start', bg=self.__color_btndefault, activebackground=self.__color_btndefault)
            self._analyzer.parameter_queue.put(['logstop'])
        else:
            self.__logging_status = True
            self.__logging_startstopBtn.configure(text = 'Stop', bg=self.__color_btngreen, activebackground=self.__color_btngreen)
            self._analyzer.parameter_queue.put(['logstart'])
    
    def __logging_clear(self):
        self._analyzer.parameter_queue.put(['reset'])
    
    def __logging_browse(self):
        browsed = filedialog.asksaveasfilename(parent=self.master, title="Choose a file for saving logged SSMB data", initialfile=self.__logging_path.get(), filetypes=[('HDF5 file','*.hdf5')], defaultextension='.hdf5')
        if type(browsed) is str:
            if len(browsed) > 0:
                self.__logging_path.set(browsed)
    
    def __logging_save(self):
        if len(self.__logging_path.get()) > 0:
            self._analyzer.parameter_queue.put(['save', self.__logging_path.get()])

    
    def close(self):
        if tk.messagebox.askyesno('Quit?', 'Do you really want to quit?'):
            self.shutdown()
            
    def shutdown(self):
        ### stop all control loops ###
        # (if objects do not exist due to failed initialization, print a warning)
        try:
            self._ctrl.stop()
        except AttributeError:
            print('Warning: Tried to close nonexistent scope connection')
            
        try:
            self._analyzer.stop()
        except AttributeError:
            print('Warning: Tried to stop nonexistent data evaluation routine')
            
        try:
            self._epics.stop()
        except AttributeError:
            print('Warning: Tried to close nonexistent EPICS connection')
        
        self.loop_run = False # stop own control loop
        
        ### save most recent configuration ###
        try:
            self._cfg[self.__cfg_key]['averaginglength'] = str(self.__config_avlen.get())
            self._cfg[self.__cfg_key]['maxturns'] = str(self.__config_maxrev.get())
            self._cfg[self.__cfg_key]['sidepeaks'] = str(self.__config_maxpeak.get())
            self._cfg[self.__cfg_key]['windowcenter'] = str(self.__config_wincent.get())
            self._cfg[self.__cfg_key]['windowwidth'] = str(self.__config_winwidth.get())
            if self.__config_centerposmode == 'manual':
                self._cfg[self.__cfg_key]['centerpeak_pos'] = str(self.__config_centerpos.get())
            else:
                self._cfg[self.__cfg_key]['centerpeak_pos'] = self.__config_centerposmode
                
            self._cfg[self.__cfg_key]['savedest'] = self.__rawdata_path.get()
            self._cfg[self.__cfg_key]['logdest'] = self.__logging_path.get()
            
            with open(self.__cfg_name, 'w') as cfgfile:
                self._cfg.write(cfgfile) # save changed configuration to file
        except KeyError:
            print(f'Warning: Cannot write to the configuration file "{self.__cfg_name}"!')
        
        ### close the application and destroy the window. End of program. ###
        self.master.quit()
        self.master.destroy()
        

## if this file is run, start Window in testing mode (continue running after connection failure):
if __name__ == '__main__':
    root = tk.Tk()
    app = SSMBWindow(root, testing=True)
    root.after(100, app.startup)
    root.mainloop()
