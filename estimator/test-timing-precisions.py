# Testing the precision of taking the system clock.

import time

active1 = True
active2 = True
t2 = time.time()
tt2 = time.clock()
while active1 or active2:
    t1 = t2
    t2 = time.time()
    if t1!=t2 and active1:
        print("time.time resolution: {:.10f}s".format(t2-t1))
        active1 = False
        
    tt1 = tt2
    tt2 = time.clock()
    if tt1!=tt2 and active2:
        print("time.clock resolution: {:.10f}s".format(tt2-tt1))
        active2 = False

