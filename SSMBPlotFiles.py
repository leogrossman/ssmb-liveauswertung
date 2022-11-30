import sys
import os
import configparser

import pandas as pd
from datetime import datetime
from matplotlib import pyplot as plt

import SSMBSequenceAnalyzerUtilities as sequtil
import SSMBTraceAnalyzerUtilities as util
import TektronixWfmImport as tek

USAGE_TEXT = '''Usage:
python SSMBPlotFiles.py INPUT_FOLDER [TIMESTAMPS ...] [channels=CH3[+,]]

Plot raw SSMB scope traces from INPUT_FOLDER for files closest to the given TIMESTAMPS.
------------------------------

INPUT_FOLDER:      path to folder from which scope data is read
                   (if not given use current working directory)

TIMESTAMPS:        space separated list of timestamps for which plots should be created. Format HH:MM:SS or HH:MM

channels:          specifies which scope channels to plot; if not given using CH3.
                   Channels separated by `+` are displayed in the same plot,
                   channels separated by `,` are shown in different plots.
                   (example: `channels=CH3+MATH2,CH4+MATH1` will produce two plots with CH3 & MATH2 and CH4 & MATH1)
'''

def print_usage():
    print(USAGE_TEXT)

def read_data(filepath, timecolumn = 'TIME'):
    '''
    Import .csv or tektronix .wfm file with oscilloscope data as pandas DataFrame.
    
    Parameters
    ----------
    filepath : string or list of strings
        Path to the file from where to import the tracedata. must be '.csv' of '.wfm'. If list of file paths, must be '.wfm' files to multiple channels of the same measurement.
    '''
    if type(filepath) is not str:
        trace = tek.read_multi_channel(filepath)
    elif filepath[::-1].find('mfw.') == 0: # if filepath ends with '.wfm'
        trace = tek.read_single_channel(filepath)
    
    elif filepath[::-1].find('vsc.') == 0: # if filepath ends with '.csv'
        for i in range(11,-1,-1): # number of header rows should be 11, but could be less for single column files
            try:
                trace = pd.read_csv(filepath, skiprows = i)
            except pd.errors.EmptyDataError:
                raise RuntimeError("csv import failed, no data in file")
            try:
                trace[timecolumn] # this fails with KeyError if "timecolum" key not present, which means we have skipped to many rows
                return trace
            except KeyError:
                print("Warning: csv import fail, reducing skiprows to", i-1)
        raise RuntimeError("csv import failed, could not resolve column names")
    else:
        raise FileNotFoundError("Provided file is not .csv or .wfm")
    return trace

def main():
##### read input folder #####
    try:
        inputfolder = sys.argv[1]
        if inputfolder[-1] != '/':
            inputfolder += '/'
        if not os.path.isdir(inputfolder):
            print("Error: First argument must be valid input folder, given folder does not exist\n")
            print_usage()
            return
            #raise RuntimeError("First argument must be valid input folder, given folder does not exist")
    except IndexError: # no more arguments after first
        print("Error: First argument must be valid input folder, no arguments given\n")
        print_usage()
        return
        #raise RuntimeError("First argument must be valid input folder, no arguments given")
    
##### read configuration #####
    cfg = configparser.ConfigParser()
    cfg.read("SSMBFileAnalysisConfig.ini")
    
    file_read_time_tolerance = 800
    try:
        file_read_time_tolerance = int(cfg['CURRENT']['file_read_time_tolerance'])
    except KeyError:
        print(f'Warning: Config parameter "file_read_time_tolerance" not found in ini file "SSMBFileAnalysisConfig.ini", using default "{file_read_time_tolerance}"')
    except ValueError:
        print(f'Warning: Config parameter "file_read_time_tolerance" in ini file "SSMBFileAnalysisConfig.ini" has invalid value, using default "{file_read_time_tolerance}"')
   
##### searching files to load #####
    print("Searching for files...")
    # # # look for .wfm files # # #
    wfmfiles = [inputfolder+filen for filen in os.listdir(inputfolder) if filen[::-1].find('mfw.') == 0]
    if len(wfmfiles) > 0:
        inputfiles = sequtil.sort_wfm_files(wfmfiles, file_read_time_tolerance)
    else:
        csvfiles = [inputfolder+filen for filen in os.listdir(inputfolder) if filen[::-1].find('vsc.') == 0]
        if not len(csvfiles) > 0:
            raise RuntimeError("No .wfm or .csv files in specified directory")
        inputfiles = sorted(csvfiles, key=util.extractDatetimeFromDataFilename)
    print("Found total of", len(inputfiles), "data sets in input folder.")
    
##### read input parameters #####
    channels = []
    for a in sys.argv[2:]:        
        keyindex = a.find('channels=')
        if keyindex >= 0:
            channelstr = a[keyindex+9:]
            channelgroups = channelstr.split(',')
            for channelgroup in channelgroups:
                channels.append(channelgroup.split('+'))
            if len(channels) > 0:
                break
    if len(channels) == 0:
        print('Warning, no parameter `channels` given, using "CH3"')
        channels.append(['CH3'])
    
    plottimes = []
    plotfiles = []
    try:
        for a in sys.argv[2:]:
            try:
                plottime = datetime.strptime(a, '%H:%M:%S').time()
                plottimes.append(plottime)
            except ValueError: # parsing to datetime failed, try other format
                try:
                    plottime = datetime.strptime(a, '%H:%M').time()
                    plottimes.append(plottime)
                except ValueError: # parsing to datetime failed, try next argument
                    pass
    except IndexError: # no more arguments after first
        pass
    
    if len(plottimes) == 0:
        print("Warning: no valid timestrings in the format HH:MM:SS or HH:MM found, plotting first, middle and last files in input folder")
        plotfiles.append(inputfiles[0])
        if len(inputfiles) > 2:
            plotfiles.append(inputfiles[len(inputfiles)//2])
        if len(inputfiles) > 1:
            plotfiles.append(inputfiles[-1])
    else:
        file0 = inputfiles[0]
        if type(file0) is not str:
            file0 = file0[0]
        date = util.extractDatetimeFromDataFilename(file0)
        for plottime in plottimes:
            plotdatetime = datetime.combine(date, plottime)
            i=0
            k=0
            j=len(inputfiles)-1
            while j-i > 1:
                k = (j-i)//2 + i
                if type(inputfiles[k]) is str:
                    ktime = util.extractDatetimeFromDataFilename(inputfiles[k])
                else:
                    ktime = util.extractDatetimeFromDataFilename(inputfiles[k][0])
                if ktime == plotdatetime:
                    break
                if ktime > plotdatetime:
                    j=k
                if ktime < plotdatetime:
                    i=k
            plotfiles.append(inputfiles[k])        
    
    for plotfile in plotfiles:
        if type(plotfile) is str:
            plottime = util.extractDatetimeFromDataFilename(plotfile)
        else:
            plottime = util.extractDatetimeFromDataFilename(plotfile[0])
        trace = read_data(plotfile)
        c=0
        for channelsinner in channels:
            fig = plt.figure()
            ax = fig.gca()
            for channel in channelsinner:
                try:
                    trc = trace[channel]
                    ax.plot(trace['TIME'], trc, f'C{c}', label=channel)
                except KeyError:
                    print(f"Error: File {plotfile}: Failed to plot channel {channel}")
                c+=1
            ax.grid()
            ax.legend()
            ax.set_title(plottime.strftime("%H:%M:%S") + " - channels " + ', '.join(channelsinner))
            ax.set_xlabel("TIME")
            ax.set_ylabel(', '.join(channelsinner))
    plt.show()

if __name__ == '__main__':
    main()
