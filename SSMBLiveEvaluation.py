#! /usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on Wed  1 10:51:46 2022

@author: Arnold Kruschinski
"""
from tkinter import Tk
from SSMBLiveWindow import SSMBWindow

root = Tk()
app = SSMBWindow(root, plotting=True)
root.after(100, app.startup)
root.mainloop()
