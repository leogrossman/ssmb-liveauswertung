import os
import sys

import configparser

import SSMBSequenceAnalyzer as seq
import SSMBSequenceAnalyzerUtilities as sequtil
import SSMBTraceAnalyzerUtilities as util

USAGE_TEXT = '''Usage:
python SSMBAnalyzeFiles.py OUTPUT_FILE_PATH [INPUT_FOLDERS ...] [PARAMETERS key=value ...]

Do analysis of SSMB scope data to yield background corrected peak heights.
------------------------------

OUTPUT_FILE_PATH:  path to output file, must be *.hdf5

INPUT_FOLDERS:     space separated list of folders from which scope data is read
                   (if none given look in current working directory)
                  
PARAMETERS:        space separated parameters for analysis in the form key=value
                   (parameters specified here override parameters from the config INI file)
                   
Parameters that can be set are:
    filtering                : Boolean    
    filterwidth              : Float (nanoseconds) (only used if filtering = True)
    bgfitorder               : Integer (only used if filtering = False)

    averaginglength          : Integer
    maxturns                 : Integer
    sidepeaks                : Integer
    windowcenter             : Float (nanoseconds)
    windowwidth              : Float (nanoseconds)
    centerpeak_pos           : Float (nanoseconds) or "automatic", "fixed", "center"
        
    timecolumn_name          : String
    harm1column_name         : String
    harm2column_name         : String
    lasercolumn_name         : String
    invertharm1              : Boolean
    invertharm2              : Boolean
    invertlaser              : Boolean
    harm_for_auto_centerpeak : Integer
    turn_for_auto_centerpeak : Integer
    
    laser_threshold          : Float
    chunk_gap                : Float (seconds)

    plot                     : Boolean   
    plotmax                  : Integer
    plot_all_chunks          : Boolean
    plotfolder               : String
'''

def print_usage():
    print(USAGE_TEXT)

def main():
    '''
    main script when running this program to analyze several files.

    Command line arguments:
    [1]  - output hdf5 file path
    [2:] - input folders to read .csv or .wfm files from (for arguments w/o "=")
    [2:] - parameters for analysis (in the form key=value for argumemts w/  "=")
    '''
##### reading arguments #####
    try:
        outputpath = sys.argv[1] #TODO: check if outputpath is valid
        outputdir = os.path.dirname(outputpath)
        if len(outputdir) > 0: # if empty only a filename in current directory was given, which works.
            if not os.path.isdir(outputdir):
                print('Error: OUTPUT_FILE_PATH directory does not exist!\n')
                print_usage()
                return
        if not outputpath[-5:] == '.hdf5':
            print('Error: OUTPUT_FILE_PATH does not point to *.hdf5 file!\n')
            print_usage()
            return
    except IndexError: # no arguments provided
        print_usage()
        return
    
    inputfolders = []
    try:
        for a in sys.argv[2:]:
            inputfolder = a
            if inputfolder[-1] != '/':
                inputfolder += '/'
            if os.path.isdir(inputfolder):
                inputfolders.append(inputfolder)
    except IndexError: # no more arguments after first
        pass
    
    if len(inputfolders) == 0:
        print("Warning: no valid input folders given, using current working directory")
        inputfolder = os.getcwd()
        if inputfolder[-1] != '/':
            inputfolder += '/'
        inputfolders.append(inputfolder)
    else:
        print("Following input folders are used:")
        for folder in inputfolders:
            print(folder)
        
##### read configuration #####
    cfg = configparser.ConfigParser()
    cfg.read("SSMBFileAnalysisConfig.ini")
    
    file_read_time_tolerance = 800
    try:
        file_read_time_tolerance = int(cfg['CURRENT']['file_read_time_tolerance'])
    except KeyError:
        print(f'Warning: Config parameter "file_read_time_tolerance" not found in ini file "ConfigSSMBSequenceAnalyzer.ini", using default "{file_read_time_tolerance}"')
    except ValueError:
        print(f'Warning: Config parameter "file_read_time_tolerance" in ini file "ConfigSSMBSequenceAnalyzer.ini" has invalid value, using default "{file_read_time_tolerance}"')
        
    
##### searching files to load #####
    # should there also be a way to directly supply a list of files or filename filters?
    print("Searching for files...")
    # # # look for .wfm files # # #
    wfmfiles = [fold+filen for fold in inputfolders for filen in os.listdir(fold) if filen[::-1].find('mfw.') == 0]
    if len(wfmfiles) > 0:
        inputfiles = sequtil.sort_wfm_files(wfmfiles, file_read_time_tolerance)
    else:
        csvfiles = [fold+filen for fold in inputfolders for filen in os.listdir(fold) if filen[::-1].find('vsc.') == 0]
        if not len(csvfiles) > 0:
            raise RuntimeError("No .wfm or .csv files in specified directory")
        inputfiles = sorted(csvfiles, key=util.extractDatetimeFromDataFilename)
    print("Found total of", len(inputfiles), "data sets in input folders.")
    
##### setting parameters ######
    
    boolean = lambda s: s.lower() in ('true', 't', 'yes', 'y')
    booleanTrue = lambda s: s.lower() not in ('false', 'f', 'no', 'n')
    
    params = dict(filtering = True, averaginglength = 10, maxturns = 9, sidepeaks = 2,
                  windowcenter = 60, windowwidth=30, centerpeak_pos = 'automatic', plot=False)
    types = [[boolean], [int], [int], [int], [int, float], [int, float], [int, float, str], [boolean]]
    
    advancedparams = dict(timecolumn_name = "TIME", harm1column_name = "CH3", harm2column_name= "CH4", lasercolumn_name = "CH1",
                          invertharm1 = False, invertharm2 = False, invertlaser = False, harm_for_auto_centerpeak = 1, turn_for_auto_centerpeak = 1, laser_threshold = 0.03, chunk_gap = 5)
    advancedtypes = [[str], [str], [str], [str], [boolean], [boolean], [boolean], [int], [int], [int, float], [int, float]]
    
    filterparams = dict(filterwidth = 2)
    filtertypes = [[int, float]]
    fitparams = dict(bgfitorder = 2)
    fittypes = [[int]]
    
    plotparams = dict(plotmax=20, plot_all_chunks = True, plotfolder='Testplots/')
    plottypes = [[int], [booleanTrue], [str]]
    
    '''
    # old procedure (prompt for parameters):
    set_parameters(params, types)
    if params['filtering']:
        print("You specified 'filtering' = True.")
        sequtil.prompt_parameters(filterparams, filtertypes)
    else:
        print("You specified 'filtering' = False, will do background fit.")
        sequtil.prompt_parameters(fitparams, fittypes)
        
    if params['plot']:
        print("You specified 'plot' = True.")
        sequtil.prompt_parameters(plotparams, plottypes)
        
    advanced = boolean(input("Do you want to specify advanced parameters? [y/n] "))
    if advanced:
        sequtil.prompt_parameters(advancedparams, advancedtypes)
    '''
    # read from command line arguments, if not found from config:
    for p, t in zip([params, advancedparams, filterparams, fitparams, plotparams], [types, advancedtypes, filtertypes, fittypes, plottypes]):
        for k, tt in zip(p, t):
            success = False
            try:
                for arg in sys.argv[2:]:
                    keyindex = arg.find(k+'=')
                    if keyindex >= 0:
                        try:
                            success = sequtil.parse_parameter(p, k, arg[keyindex+len(k)+1:], tt)
                            if success:
                                break
                            else:
                                print(f'Warning: Parameter "{k}" is specified in command line arguments with invalid value, looking in other arguments then using config value')
                        except IndexError:
                            print(f'Warning: Parameter "{k}" is specified in command line arguments without a value, looking in other arguments then using config value')
            except IndexError:
                pass # no arguments, continue with config
            
            if not success:
                try:
                    if not sequtil.parse_parameter(p, k, cfg['CURRENT'][k], tt):
                        print(f'Warning: Parameter "{k}" in ini file "ConfigSSMBSequenceAnalyzer.ini" has invalid value, using code default "{p[k]}"')
                except KeyError:
                    print(f'Warning: Did not find parameter "{k}" in ini file "ConfigSSMBSequenceAnalyzer.ini", using code default "{p[k]}"')
    
    # present parameters
    print()
    print("Parameters for SequenceAnalyzer:\n")
    for k in params:
        print(k, '=', params[k])
        
    if params['filtering']:
        print("\nParameters for filtering:\n")
        for k in filterparams:
            print(k, '=', filterparams[k])
    else:
        print("\nParameters for background fit:\n")
        for k in fitparams:
            print(k, '=', fitparams[k])
            
    if params['plot']:
        print("\nParameters for plotting:\n")
        for k in plotparams:
            print(k, '=', plotparams[k])
            
    print("\nAdvanced Parameters:\n")
    for k in advancedparams:
        print(k, '=', advancedparams[k])

##### starting sequence #####
    try:
        input("Press Enter to start, Ctrl+C to cancel ... ")
    except EOFError:
        print("Canceled")
        return
    SqAna = seq.SequenceAnalyzer(**params, **fitparams, **filterparams, **plotparams, **advancedparams)
    for inputfile in inputfiles:
        SqAna.next_analysis(filepath = inputfile)
    SqAna.save_peakdata_to_hdf(outputpath)

if __name__ == "__main__":
    main()
