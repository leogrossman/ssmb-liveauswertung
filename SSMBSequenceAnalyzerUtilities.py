from datetime import timedelta,datetime
import SSMBTraceAnalyzerUtilities as util

def parse_parameter(params_dict, key, string_value, allowed_types):
    if len(string_value) != 0: # we do not accept an empty string, as this should produce the default => do nothing, keep current value
        for t in allowed_types:
            try:
                params_dict[key] = t(string_value)
                return True
            except ValueError:
                pass # failed, try next type or skip to default
    return False
    
def prompt_parameters(params, types):
    """
    Routine to prompt user for parameters
    """
    for k, tt in zip(params, types):
        inp = input(f"Please set parameter {k} (Default {params[k]}): ")
        parse_parameter(params, k, inp, tt)

def sort_wfm_files(filelist, time_threshold_ms = 800):
    time_threshold = timedelta(milliseconds=time_threshold_ms)
    channels = sorted(set(util.extractChannelNameFromDataFilename(f) for f in filelist))
        # all channel names present in file list, sorted alphabetically
    groupedfilelist = [sorted([ f for f in filelist if ch == util.extractChannelNameFromDataFilename(f)], key=util.extractDatetimeFromDataFilename) for ch in channels]
        # file list grouped by channel names and sorted by time extracted from filename
    groupedtimelist = [[util.extractDatetimeFromDataFilename(f) for f in filegroup] for filegroup in groupedfilelist]
        # datetimes from all files (same structure as groupedfilelist)
    outputlist = []
    for g, group, timegroup in zip(range(len(groupedfilelist)), groupedfilelist, groupedtimelist):
        for _ in range(len(group)):
            # for every element in the current "leading" group:
            currentfile = group[0]
            del group[0]
            currenttime = timegroup[0]
            try:
                nexttime = timegroup[1]
            except IndexError:
                nexttime = datetime(9999,12,31)
            del timegroup[0]
            currentlist = [currentfile]
            for othergroup, othertimegroup in zip(groupedfilelist[g+1:], groupedtimelist[g+1:]):
                # for all following groups:
                # find the first file with later datetime
                #(groups are sorted with increasing time! This is necessary here!)
                minindex = -1
                for i, othertime in enumerate(othertimegroup):
                    diff = othertime - currenttime
                    if diff >= timedelta(0):
                        minindex = i
                        break
                # and if the time difference is smaller than the threshold, add it to set, but only if the next file from the leading group is not also before it:
                if diff < time_threshold and minindex >= 0 and othertime < nexttime:
                    currentlist.append(othergroup[minindex])
                    del othergroup[minindex]
                    del othertimegroup[minindex]
            outputlist.append(currentlist)
    return sorted(outputlist, key = lambda x: min([util.extractDatetimeFromDataFilename(y) for y in x]))
        # sort output file list by lowest datetime in each set
