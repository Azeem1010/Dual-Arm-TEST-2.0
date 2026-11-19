import re,sys,glob,os,time
rows=[]
for f in sorted(glob.glob(os.path.expanduser('~/.ros/log/python3_*.log')),key=os.path.getmtime):
    if os.path.getmtime(f)<time.mktime((2026,11,18,0,0,0,0,0,-1)): continue
    cur=None; redesc=False
    for line in open(f,errors='ignore'):
        m=re.search(r'arm1 to \((-?[\d.]+), (-?[\d.]+), 0\.0163\d*\): arrived z ([\d.]+) mm .*xy error ([\d.]+) mm, joint error counts \[([^\]]+)\]',line)
        if 'stopped' in line and 'descending again' in line and 'arm1 to' in line: redesc=True
        if m:
            if cur: rows.append(cur)
            cur=dict(f=os.path.basename(f)[8:14],x=float(m[1])*1000,y=float(m[2])*1000,z=float(m[3]),xy=float(m[4]),j=m[5],re=redesc,res='?'); redesc=False
            continue
        if cur and cur['res']=='?':
            if 'arm2 B contact' in line: cur['res']='OK'
            elif 'Placement in zone B' in line or 'no suction' in line: cur['res']='FAIL'
            elif 'Task stopped' in line or 'canceled' in line: cur['res']='stop'
    if cur: rows.append(cur)
for r in sorted(rows,key=lambda r:r['y']):
    print(f"{r['f']} x{r['x']:7.1f} y{r['y']:6.1f}  z{r['z']:5.1f} xyerr{r['xy']:4.1f} redesc={'Y' if r['re'] else '-'} j[{r['j']}] {r['res']}")
