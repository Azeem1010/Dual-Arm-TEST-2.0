import os,sys,termios,time,select,statistics as st
p=sys.argv[1]; fd=os.open(p,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=a[1]=a[3]=0; a[2]=termios.CS8|termios.CREAD|termios.CLOCAL; a[4]=a[5]=termios.B1000000
a[6][termios.VMIN]=0; a[6][termios.VTIME]=0; termios.tcsetattr(fd,termios.TCSANOW,a); termios.tcflush(fd,termios.TCIOFLUSH)
def tx(cmd):
    t=time.perf_counter(); os.write(fd,(cmd+'\n').encode()); buf=b''
    while b'\n' not in buf:
        r,_,_=select.select([fd],[],[],0.5)
        if not r: return None,buf
        buf+=os.read(fd,256)
    return (time.perf_counter()-t)*1000,buf.strip()
print('VERSION',tx('VERSION'))
for cmd in ('READ,arm1','READ,arm2'):
    ts=[];bad=0
    for i in range(200):
        dt,r=tx(cmd)
        if dt is None or not r.startswith(b'POS'): bad+=1; continue
        ts.append(dt)
    ts.sort(); print(cmd,'n',len(ts),'bad',bad,'min %.1f med %.1f p90 %.1f max %.1f ms'%(ts[0],st.median(ts),ts[int(.9*len(ts))],ts[-1]), 'last',r)
