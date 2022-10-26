# -*- coding: utf-8 -*-
"""
Created on Thu Jul 21 15:19:00 2022

@author: Arnold Kruschinski
"""

import threading
import queue

from SSMBSequenceAnalyzer import SequenceAnalyzer

class SSMBLiveAnalyzer:
    def __init__(self, epics, logging=False, **initialparameters):
        self.data_queue = queue.Queue() # new queue for feeding raw data from the scope control module
        self.__PV = epics.PV            # reference to the epics access module (passed here with initialization)
        self.__analyzer = SequenceAnalyzer(**initialparameters)  # initialize SequenceAnalyzer with starting parameters
        self.parameter_queue = queue.Queue()  # new queue to input new parameters from the main window
        self.result_queue = queue.LifoQueue() # new queue to output evaluated data to the main window (Lifo: always use newest data, display will be slower than evaluation)
        self.maxvalue_queue = queue.Queue()   # new queue to output evaluated max peak heights for scope scale adjustment
        self.__epics_queue = epics.data_queue # get queue to output evaluated data to the epics access module (passed here with initialization)
        self.go = False
        self.logging = logging
        self.__thread = threading.Thread(target=self.__analysis_loop) # new thread for data evaluation
        
    def start(self):
        self.go = True
        self.__thread.start()
    
    def stop(self):
        self.go = False
        
    def get_parameters(self):
        return self.__analyzer.get_parameters()
        
    def __analysis_loop(self):
        '''
        Main loop to be called in a new thread, evaluating data in the data_queue and outputting the result into result_queue and __epics_queue.
        '''
        while self.go:
            ### check for new parameter change commands in the parameter queue ###
            while self.parameter_queue.qsize(): # iterate as long as there are items to get
                arguments = self.parameter_queue.get_nowait()
                command = arguments[0]
                del arguments[0]
                try:
                    if command == 'avglen':
                        self.__analyzer.set_averaging_length(*arguments)
                    elif command == 'turns':
                        self.__analyzer.set_max_turns(*arguments)
                    elif command == 'peaks':
                        self.__analyzer.set_sidepeaks(*arguments)
                    elif command == 'window':
                        self.__analyzer.set_window(*arguments)
                    elif command == 'centerpos':
                        self.__analyzer.set_centerpeak_pos(*arguments)
                    elif command == 'logstart':
                        self.logging = True
                    elif command == 'logstop':
                        self.logging = False
                    elif command == 'save':
                        self.__analyzer.save_peakdata_to_hdf(*arguments)
                    elif command == 'reset':
                        self.__analyzer.reset_sequence()
                except (TypeError, ValueError) as e:
                    print(f'Error: SSMBLiveAnalyzer: Invalid parameter change command "{command}", {arguments}. Error message:')
                    print(type(e), e)
                except OSError as e:
                    print(f'Error: SSMBLiveAnalyzer: Invalid file destination {arguments}. Error message:')
                    print(type(e), e)
            ### once all commands are completed, start checking for new data ###
            try:
                date, data = self.data_queue.get(timeout = 0.1)
                self.__analyzer.next_analysis(data = data, date_time = date, log_peakdata = self.logging, frf=self.__PV.get_frf())
                self.result_queue.put((self.__analyzer.get_current_trace_analysis(), self.__analyzer.get_current_peakdata(), self.__analyzer.get_centerpeak_pos(), self.__analyzer.get_peakdata_length()))
                self.__epics_queue.put(self.__analyzer.get_current_peakdata())
                self.maxvalue_queue.put((self.__analyzer.get_current_trace_analysis().get_raw_max_peak(harmonic=1), self.__analyzer.get_current_trace_analysis().get_raw_max_peak(harmonic=2)))
            except queue.Empty:
                pass # no new data, continue
