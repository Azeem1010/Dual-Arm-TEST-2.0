import sys,numpy as np,rosbag2_py
from rclpy.serialization import deserialize_message
from control_msgs.msg import JointTrajectoryControllerState
from rcl_interfaces.msg import Log
bag=sys.argv[1]; out=sys.argv[2]
r=rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=bag,storage_id='mcap'),rosbag2_py.ConverterOptions('cdr','cdr'))
r.set_filter(rosbag2_py.StorageFilter(topics=['/arm1_controller/controller_state','/arm2_controller/controller_state','/rosout']))
data={'arm1':[],'arm2':[]}; logs=[]
while r.has_next():
    topic,raw,t=r.read_next()
    if topic=='/rosout':
        m=deserialize_message(raw,Log)
        if m.name=='dual_arm_coordinator': logs.append((t/1e9,m.msg))
        continue
    m=deserialize_message(raw,JointTrajectoryControllerState)
    arm=topic.split('/')[1][:4]
    data[arm].append([t/1e9]+list(m.reference.positions)+list(m.feedback.positions)+list(m.reference.velocities or [0]*4))
names=None
for arm,v in data.items():
    a=np.array(v); np.save(f'{out}/{arm}.npy',a); print(arm,a.shape)
with open(f'{out}/coord_log.txt','w') as f:
    for t,msg in logs: f.write(f'{t:.3f} {msg}\n')
print('logs',len(logs))
