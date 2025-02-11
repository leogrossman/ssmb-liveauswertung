#import dateutil
from datetime import datetime, timedelta
import os

def extractDatetimeFromDataModtime(full_path_filename):
    return(datetime.fromtimestamp(os.path.getmtime(full_path_filename)))

#def extractDatetimeFromDataFilename(filename):
    #scopetimestring=filename.split(".")[0].split("_")[-1] # timestring is before the *first* '.' and after a '_'. *NOT* the last '.' in '.csv' , this is a bug in the scope
    #year=int(scopetimestring[0:4])                        # ==> NO! it is before the second-to last '.' if there are more than 1 '.'s!
    #month=int(scopetimestring[4:6])
    #day=int(scopetimestring[6:8])
    #hour=int(scopetimestring[8:10])
    #minute=int(scopetimestring[10:12])
    #second=int(scopetimestring[12:14])
    #microsecond=int(scopetimestring[14:])*1000
    #return(datetime(year,month,day,hour,minute,second,microsecond))
    #todo restore timezoneinfo?
    
def extractDatetimeFromDataFilename(filename):
    scopetimestring = filename.split(".")[-2].split("_")[-1]
    return datetime.strptime(scopetimestring, '%Y%m%d%H%M%S%f')

def extractChannelNameFromDataFilename(filename): # works only for .wfm files where the channel name is included automatically 
    chname = filename.split(".")[-2].split("_")[-1]
    try:
        int(chname) # if final_string is an integer, channel name is at second-to-last position (timestring is at last)
        chname = filename.split(".")[-2].split("_")[-2]
    except ValueError:
        pass # if final_string is not an integer, channel name is at last position
    return chname.upper()

def format_plusminus(number):
    if number == 0:
        return '0'
    letter = 'm' if number < 0 else 'p'
    return letter+str(abs(number))

