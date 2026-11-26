import numpy as np,sys
S=sys.argv[1]; arm=sys.argv[2]; t0=float(sys.argv[3]); t1=float(sys.argv[4]); C=1023/np.radians(300)
a=np.load(f'{S}/{arm}.npy'); t=a[:,0]; w=(t>=t0)&(t<=t1)
tt=t[w]-t0; ref=a[w,1:5]*C; fb=a[w,5:9]*C
keep=np.r_[True,np.any(np.diff(fb,axis=0)!=0,axis=1)]; tt,ref,fb=tt[keep],ref[keep],fb[keep]
vr=np.gradient(ref,tt,axis=0)
print(' t     ref_lift  fb_lift  err  vref | ref_elb fb_elb err | ref_pan fb_pan err  | speed_lift(driver formula)')
for i in range(0,len(tt),3):
    e=ref[i]-fb[i]; sp=np.clip(np.ceil(np.maximum(1.2*abs(vr[i,1]),abs(e[1])/0.25)/2.2698),20,300)
    print(f'{tt[i]:5.2f} {ref[i,1]:8.1f} {fb[i,1]:8.1f} {e[1]:5.1f} {vr[i,1]:6.0f} | {ref[i,2]:7.1f} {fb[i,2]:7.1f} {e[2]:5.1f} | {ref[i,0]:7.1f} {fb[i,0]:7.1f} {e[0]:5.1f} | {sp:4.0f}')
# dominant frequency of lift error ripple
e=ref[:,1]-fb[:,1]; dt=np.median(np.diff(tt)); k=int(0.5/dt); r=e-np.convolve(e,np.ones(k)/k,'same'); r=r[k:-k]
f=np.fft.rfftfreq(len(r),dt); P=np.abs(np.fft.rfft(r*np.hanning(len(r))))
print('dominant lift ripple freq %.1f Hz'%f[1+np.argmax(P[1:])])
