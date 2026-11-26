import numpy as np,re,sys
S=sys.argv[1]; C=1023/np.radians(300)   # counts per rad
logs=[l.split(' ',1) for l in open(f'{S}/coord_log.txt')]
segs=[]
for i,(t,m) in enumerate(logs):
    mm=re.match(r'(arm[12]) (to \(.*0\.052\)|B above|home|slot \d above): fixed joint path, (\d+)',m)
    if mm and int(mm[3])>20:
        for t2,m2 in logs[i+1:]:
            if 'TIMING' in m2 and mm[1] in m2: break
        segs.append((mm[1],m.split(':')[0][len(mm[1])+1:][:28],float(t),float(t2)))
J=['pan','lift','elbow','wrist']
for arm,label,t0,t1 in segs:
    a=np.load(f'{S}/{arm}.npy'); t=a[:,0]
    # controller_state joint order = controller 'joints' param order: pan,lift,elbow,wrist
    w=(t>=t0)&(t<=t1+1.5); tt=t[w]; ref=a[w,1:5]*C; fb=a[w,5:9]*C
    # dedupe repeated feedback samples
    keep=np.r_[True,np.any(np.diff(fb,axis=0)!=0,axis=1)|(np.diff(tt)>0.05)]
    tt,ref,fb=tt[keep],ref[keep],fb[keep]
    e=ref-fb
    moving=np.abs(np.gradient(ref[:,0],tt))+np.abs(np.gradient(ref[:,1],tt))
    out=[]
    for j in range(4):
        v=np.gradient(fb[:,j],tt); vr=np.gradient(ref[:,j],tt)
        vs=np.convolve(v,np.ones(5)/5,'same')
        # reversals of actual velocity while reference keeps one direction (|vr|>5 c/s)
        sgn=np.sign(vs); sgn[np.abs(vs)<8]=0
        nz=sgn[sgn!=0]; rev=int(np.sum(nz[1:]!=nz[:-1]))
        refnz=np.sign(vr[np.abs(vr)>5]); rrev=int(np.sum(refnz[1:]!=refnz[:-1])) if len(refnz)>1 else 0
        # ripple: error minus its 0.5 s moving average
        k=max(3,int(0.5/np.median(np.diff(tt))))
        ripple=e[:,j]-np.convolve(e[:,j],np.ones(k)/k,'same')
        rr=ripple[k:-k] if len(ripple)>2*k else ripple
        out.append(f"{J[j]} travel {abs(ref[-1,j]-ref[0,j]):5.0f} maxerr {np.max(np.abs(e[:,j])):5.1f} ripple_rms {np.std(rr):4.2f} p2p {np.ptp(rr):4.1f} vrev {rev}/{rrev}")
    print(f"{arm} {label:28s} {t1-t0:4.1f}s n={len(tt)}"); [print('   ',o) for o in out]
