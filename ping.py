#!/usr/bin/env python

"""
    A pure python ping implementation using raw socket.


    Note that ICMP messages can only be sent from processes running as root.


    Derived from ping.c distributed in Linux's netkit. That code is
    copyright (c) 1989 by The Regents of the University of California.
    That code is in turn derived from code written by Mike Muuss of the
    US Army Ballistic Research Laboratory in December, 1983 and
    placed in the public domain. They have my thanks.

    Bugs are naturally mine. I'd be glad to hear about them. There are
    certainly word - size dependenceies here.

    Copyright (c) Matthew Dixon Cowles, <http://www.visi.com/~mdc/>.
    Distributable under the terms of the GNU General Public License
    version 2. Provided with no warranties of any sort.

    Original Version from Matthew Dixon Cowles:
      -> ftp://ftp.visi.com/users/mdc/ping.py

    Rewrite by Jens Diemer:
      -> http://www.python-forum.de/post-69122.html#69122

    Rewrite by George Notaras:
      -> http://www.g-loaded.eu/2009/10/30/python-ping/

    Revision history
    ~~~~~~~~~~~~~~~~

    August 16, 2016
    ---------------
    - Modified code from http://www.routereflector.com/2014/08/network-ping-with-delay-jitter-and-mos/
    - Revised Nagios output a bit to conform to expectations of check_mk
    - Commented out rrd code as I don't have the right libraries installed for that
    - Added src_addr: ping uses a specific interface (allows use of linux policy based routing)
    - Added src_name: used in output documentation

    November 8, 2009
    ----------------
    Improved compatibility with GNU/Linux systems.

    Fixes by:
     * George Notaras -- http://www.g-loaded.eu
    Reported by:
     * Chris Hallman -- http://cdhallman.blogspot.com

    Changes in this release:
     - Re-use time.time() instead of time.clock(). The 2007 implementation
       worked only under Microsoft Windows. Failed on GNU/Linux.
       time.clock() behaves differently under the two OSes[1].

    [1] http://docs.python.org/library/time.html#time.clock

    May 30, 2007
    ------------
    little rewrite by Jens Diemer:
     -  change socket asterisk import to a normal import
     -  replace time.time() with time.clock()
     -  delete "return None" (or change to "return" only)
     -  in checksum() rename "str" to "source_string"

    November 22, 1997
    -----------------
    Initial hack. Doesn't do much, but rather than try to guess
    what features I (or others) will want in the future, I've only
    put in what I need now.

    December 16, 1997
    -----------------
    For some reason, the checksum bytes are in the wrong order when
    this is run under Solaris 2.X for SPARC but it works right under
    Linux x86. Since I don't know just what's wrong, I'll swap the
    bytes always and then do an htons().

    December 4, 2000
    ----------------
    Changed the struct.pack() calls to pack the checksum and ID as
    unsigned. My thanks to Jerome Poincheval for the fix.


    Last commit info:
    ~~~~~~~~~~~~~~~~~
    $LastChangedDate: $
    $Rev: $
    $Author: $
"""


import os, sys, socket, struct, select, time, datetime, getopt

# From /usr/include/linux/icmp.h; your milage may vary.
ICMP_ECHO_REQUEST = 8 # Seems to be the same on Solaris.


def checksum(source_string):
    """
    I'm not too confident that this is right but testing seems
    to suggest that it gives the same answers as in_cksum in ping.c
    """
    sum = 0
    countTo = (len(source_string)/2)*2
    count = 0
    while count<countTo:
        thisVal = ord(source_string[count + 1])*256 + ord(source_string[count])
        sum = sum + thisVal
        sum = sum & 0xffffffff # Necessary?
        count = count + 2

    if countTo<len(source_string):
        sum = sum + ord(source_string[len(source_string) - 1])
        sum = sum & 0xffffffff # Necessary?

    sum = (sum >> 16)  +  (sum & 0xffff)
    sum = sum + (sum >> 16)
    answer = ~sum
    answer = answer & 0xffff

    # Swap bytes. Bugger me if I know why.
    answer = answer >> 8 | (answer << 8 & 0xff00)

    return answer


def receive_one_ping(my_socket, ID, timeout):
    """
    receive the ping from the socket.
    """
    timeLeft = timeout
    while True:
        startedSelect = time.time()
        whatReady = select.select([my_socket], [], [], timeLeft)
        howLongInSelect = (time.time() - startedSelect)
        if whatReady[0] == []: # Timeout
            return

        timeReceived = time.time()
        recPacket, addr = my_socket.recvfrom(1024)
        icmpHeader = recPacket[20:28]
        type, code, checksum, packetID, sequence = struct.unpack(
            "bbHHh", icmpHeader
        )
        if packetID == ID:
            bytesInDouble = struct.calcsize("d")
            timeSent = struct.unpack("d", recPacket[28:28 + bytesInDouble])[0]
            return timeReceived - timeSent

        timeLeft = timeLeft - howLongInSelect
        if timeLeft <= 0:
            return


def send_one_ping(my_socket, dest_addr, ID):
    """
    Send one ping to the given >dest_addr<.
    """
    dest_addr  =  socket.gethostbyname(dest_addr)

    # Header is type (8), code (8), checksum (16), id (16), sequence (16)
    my_checksum = 0

    # Make a dummy heder with a 0 checksum.
    header = struct.pack("bbHHh", ICMP_ECHO_REQUEST, 0, my_checksum, ID, 1)
    bytesInDouble = struct.calcsize("d")
    data = (192 - bytesInDouble) * "Q"
    data = struct.pack("d", time.time()) + data

    # Calculate the checksum on the data and the dummy header.
    my_checksum = checksum(header + data)

    # Now that we have the right checksum, we put that in. It's just easier
    # to make up a new header than to stuff it into the dummy.
    header = struct.pack(
        "bbHHh", ICMP_ECHO_REQUEST, 0, socket.htons(my_checksum), ID, 1
    )
    packet = header + data
    my_socket.sendto(packet, (dest_addr, 1)) # Don't know about the 1


def do_one(src_addr, dest_addr, timeout):
    """
    Returns either the delay (in seconds) or none on timeout.
    """
    icmp = socket.getprotobyname("icmp")
    try:
        my_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, icmp)
    except socket.error, (errno, msg):
        if errno == 1:
            # Operation not permitted
            msg = msg + (
                " - Note that ICMP messages can only be sent from processes"
                " running as root."
            )
            raise socket.error(msg)
        raise # raise the original error

    my_ID = os.getpid() & 0xFFFF

    my_socket.bind((src_addr,0))

    send_one_ping(my_socket, dest_addr, my_ID)
    delay = receive_one_ping(my_socket, my_ID, timeout)

    my_socket.close()
    return delay


def verbose_ping(src_addr, dest_addr, timeout = 2, count = 4):
    """
    Send >count< ping to >dest_addr< with the given >timeout< and display
    the result.
    """
    for i in xrange(count):
        print "ping %s..." % dest_addr,
        try:
            delay  =  do_one(src_addr, dest_addr, timeout)
        except socket.gaierror, e:
            print "failed. (socket error: '%s')" % e[1]
            break

        if delay  ==  None:
            print "failed. (timeout within %ssec.)" % timeout
        else:
            delay  =  delay * 1000
            print "get ping in %0.4fms" % delay

#from lib import rrd

if __name__ == '__main__':
    count = 10              # Default send 10 packets
    timeout = 2             # Default timeout = 3 seconds
    src_addr = ''           # default to nearest port
    src_name = 'default'    # default to a default name
    dest_addr = '8.8.8.8'   # Default ping 8.8.8.8
    output = 'normal'       # Default human readable output
    rrd_file = None         # RRD file

    lost = 0        # Number of loss packets
    mos = 0         # Mean Opinion Score
    latency = []    # Delay values [MIN. MAX, AVG]
    jitter = []     # Jitter values [MAX, AVG]
    time_sent = []  # Timestamp when packet is sent
    time_recv = []  # Timestamp when packet is received

    help_line = 'Usage: %s -c [count] -t [timeout] -n [sourcename] -s [sourceip] -d [host] -o [normal|nagios|rrd] -f [rrd file]'
    try:
        opts, args = getopt.getopt(sys.argv[1:], ':hc:t:n:s:d:o:f:')
    except getopt.GetoptError as err:
        print help_line % sys.argv[0]
        sys.exit(1)
    for opt, arg in opts:
        if opt in '-h':
            print help_line % sys.argv[0]
            sys.exit(1)
        if opt in '-c':
            count = int(arg)
        elif opt in '-t':
            timeout = int(arg)
        elif opt in '-n':
            src_name = arg
        elif opt in '-s':
            src_addr = arg
        elif opt in '-d':
            dest_addr = arg
        elif opt in '-o':
            output = arg
        elif opt in '-f':
            rrd_file = arg

    if count <= 0:
        print "ERROR: count must be greater than zero."
        sys.exit(1)
    if timeout <= 0:
        print "ERROR: timeout must be greater than zero."
        sys.exit(1)

    for i in range(0, count):
        try:
            time_sent.append(int(round(time.time() * 1000)))
            d = do_one(src_addr, dest_addr, timeout)
            if d == None:
                lost = lost + 1
                time_recv.append(None)
                continue
            else:
                time_recv.append(int(round(time.time() * 1000)))
        except:
            print("Socket error")
            sys.exit(1)

        # Calculate Latency:
        latency.append(time_recv[i] - time_sent[i])

        # Calculate Jitter with the previous packet
        # http://toncar.cz/Tutorials/VoIP/VoIP_Basics_Jitter.html
        if len(jitter) == 0:
            # First packet received, Jitter = 0
            jitter.append(0)
        else:
            # Find previous received packet:
            for h in reversed(range(0, i)):
                if time_recv[h] != None:
                    break
            # Calculate difference of relative transit times:
            drtt = (time_recv[i] - time_recv[h]) - (time_sent[i] - time_sent[h])
            jitter.append(jitter[len(jitter) - 1] + (abs(drtt) - jitter[len(jitter) - 1]) / float(16))

    # Calculating MOS
    if len(latency) > 0:
        EffectiveLatency = sum(latency) / len(latency) + max(jitter) * 2 + 10
        if EffectiveLatency < 160:
           R = 93.2 - (EffectiveLatency / 40)
        else:
            R = 93.2 - (EffectiveLatency - 120) / 10
            # Now, let's deduct 2.5 R values per percentage of packet loss
            R = R - (lost * 2.5)
            # Convert the R into an MOS value.(this is a known formula)
        mos = 1 + (0.035) * R + (.000007) * R * (R-60) * (100-R)

    # Setting values (timeout, lost and mos are already calculated)
    lost_perc = lost / float(count) * 100
    if len(latency) > 0:
        min_latency = min(latency)
        max_latency = max(latency)
        avg_latency = sum(latency) / len(latency)
    else:
        min_latency = 'NaN'
        max_latency = 'NaN'
        avg_latency = 'NaN'
    if len(jitter) != 0:
        tot_jitter = jitter[len(jitter) - 1]
    else:
        tot_jitter = 'NaN'

    # Printing values
    if output == 'normal':
        print("Statistics for %s to %s:" %(src_name, dest_addr))
        print(" - packet loss: %i (%.2f%%)" %(lost, lost_perc))
        if type(min_latency) != str and type(max_latency) != str and type(avg_latency) != str:
            print(" - latency (MIN/MAX/AVG): %i/%i/%i" %(min_latency, max_latency, avg_latency))
        else:
            print(" - latency (MIN/MAX/AVG): %s/%s/%s" %(min_latency, max_latency, avg_latency))
        if type(tot_jitter) != str:
            print(" - jitter: %.4f" %(tot_jitter))
        else:
            print(" - jitter: %s" %(tot_jitter))
        print(" - MOS: %.1f" %(mos))
    elif output == 'nagios':
        if lost_perc == 100:
#            print('2 %s_stats lost=%.2f|delay=%i;75;100;0;%i|mos=%.1f;4.0;3.0;0.0;5.0 ' %(dest_addr, lost_perc, timeout * 1000, timeout * 1000, mos))
            print('2 %s_to_%s_loss lost=%.2f %s - no reply' %(src_name, dest_addr, lost_perc, dest_addr))
            sys.exit(2)
        else:
#            print('0 %s_stats lost=%.2f|delay=%i;75;100;0;%i|jitter=%.2f|mos=%.1f;4.0;3.0;0.0;5.0 test' %(dest_addr, lost / float(count) * 100, sum(latency) / len(latency), timeout * 1000, jitter[len(jitter) - 1 ], mos))
            print('0 %s_to_%s_loss loss=%.2f %s - %.f packets lost' %(src_name, dest_addr, lost / float(count) * 100, dest_addr, lost / float(count) * 100 ))
            print('0 %s_to_%s_delay delay=%i;75;100;0;%i %s - %i ms delay' %(src_name, dest_addr,  sum(latency) / len(latency), timeout * 1000, dest_addr, sum(latency) / len(latency) ))
            print('0 %s_to_%s_jitter jitter=%.2f %s - %.2f ms jitter' %(src_name, dest_addr,  jitter[len(jitter) - 1 ], dest_addr,  jitter[len(jitter) - 1 ] ))
            print('0 %s_to_%s_mos mos=%.1f;4.0;3.0;0.0;5.0 %s - mos score %.1f' %(src_name, dest_addr, mos, dest_addr, mos))
            sys.exit(0)
#        if lost_perc == 100:
#            print('UNREACHABLE | lost=%.2f delay=%i;75;100;0;%i mos=%.1f;4.0;3.0;0.0;5.0' %(lost_perc, timeout * 1000, timeout * 1000, mos))
#            sys.exit(2)
#        else:
#            print('OK | lost=%.2f delay=%i;75;100;0;%i jitter=%.2f mos=%.1f;4.0;3.0;0.0;5.0' %(lost / float(count) * 100, sum(latency) / len(latency), timeout * 1000, jitter[len(jitter) - 1 ], mos))
#            sys.exit(0)
    elif output == 'rrd':
        if rrd_file == None:
            print('ERROR: RRD output require a valid "-f" option.')
            sys.exit(1)
        step = '300'
#        rrd_counters = [['lost', 'GAUGE'], ['jitter', 'GAUGE'], ['latency', 'GAUGE'], ['mos', 'GAUGE']]
#        rrd.create_rrd(rrd_file, step, rrd_counters)
#        rrd_values = [lost_perc, tot_jitter, max_latency, mos]
#        rrd.update_rrd(rrd_file, rrd_values)
    else:
        print 'ERROR: output not definied.'
        sys.exit(1)

