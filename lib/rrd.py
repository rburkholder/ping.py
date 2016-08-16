#!/usr/bin/env python

import os, rrdtool

# Create an RRD file
def create_rrd(rrd_file, step, rrd_counters):
    if os.path.isfile(rrd_file):
        return True

    argv = []
    argv.append(rrd_file)
    argv.append('--step')
    argv.append(step)
    argv.append('--start')
    argv.append('0')
    for c in rrd_counters:
        argv.append("DS:%s:%s:300:U:U" %(c[0], c[1]))
    argv.append('RRA:AVERAGE:0.5:1:2880')
    argv.append('RRA:AVERAGE:0.5:5:2880')
    argv.append('RRA:AVERAGE:0.5:30:4320')
    argv.append('RRA:AVERAGE:0.5:360:5840')
    argv.append('RRA:MAX:0.5:1:2880')
    argv.append('RRA:MAX:0.5:5:2880')
    argv.append('RRA:MAX:0.5:30:4320')
    argv.append('RRA:MAX:0.5:360:5840')
    argv.append('RRA:MIN:0.5:1:2880')
    argv.append('RRA:MIN:0.5:5:2880')
    argv.append('RRA:MIN:0.5:30:4320')
    argv.append('RRA:MIN:0.5:360:5840')
    rc = rrdtool.create(argv)
    if rc:
        print rrdtool.error()
        return False
    else:
        return True

# Update the RRD file
def update_rrd(rrd_file, rrd_values):
    if not os.path.isfile(rrd_file):
        return False

    arg = 'N'
    for c in rrd_values:
        arg = arg + ':%s' %(c)
    rc = rrdtool.update(rrd_file, arg)
    if rc:
        print rrdtool.error()
        return False
    else:
        return True

