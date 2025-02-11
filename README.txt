To start the SSMB Live Data Evaluation:

 1. Make sure the SSMB scope is on
 2. run "python3 SSMBLiveEvaluation.py" (must run on Python 3.6 or newer)
 3. when the window has opened, the evaluation should run immediately if the scope is acquiring data. Modify configuration as needed.
 
EPICS variables to which evaluation results are output:
 TBD.
 
Debugging:
 If the scope cannot be found:
 check configuration file "SSMBLiveAnalysisConfig.ini": IP Address under 'scopeip' should be the actual IP Address of the scope
