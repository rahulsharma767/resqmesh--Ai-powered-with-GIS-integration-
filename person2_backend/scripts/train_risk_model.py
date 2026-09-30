from pathlib import Path
import csv, math, json, struct
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

ROOT=Path('/tmp/resqmesh/ResqQmesh-main')
AI=ROOT/'person2_backend'/'ai_engine'
AI.mkdir(parents=True,exist_ok=True)
MODEL_DIR=ROOT/'person2_backend'/'ai_engine'/'models'
MODEL_DIR.mkdir(parents=True,exist_ok=True)
DATA_DIR=ROOT/'person2_backend'/'data'/'training'
DATA_DIR.mkdir(parents=True,exist_ok=True)

FEATURES=[
 'number_of_patients','unconscious_count','critical_count','injury_severity',
 'fire_present','accident_type','traffic_level','road_block_probability',
 'distance_to_nearest_ambulance','hospital_capacity','icu_availability',
 'emergency_availability','time_of_day','location_context','route_eta_minutes'
]
# 0..2 categorical/numeric encoding conventions documented in inference.py
rng=np.random.default_rng(20260930)
n=6000
X=np.zeros((n,len(FEATURES)),dtype=np.float32)
X[:,0]=rng.integers(1,7,n)
X[:,1]=rng.binomial(2,0.18,n)
X[:,2]=rng.binomial(3,0.20,n)
X[:,3]=rng.uniform(0.1,1.0,n)
X[:,4]=rng.binomial(1,0.08,n)
X[:,5]=rng.integers(0,4,n) # 0 general, 1 trauma, 2 cardiac, 3 fire
X[:,6]=rng.integers(0,4,n) # green..red
X[:,7]=rng.uniform(0,1,n)
X[:,8]=rng.uniform(0.2,15,n)
X[:,9]=rng.uniform(0,100,n) # hospital capacity stress: 0=healthy capacity, 100=severely constrained
X[:,10]=rng.binomial(1,0.7,n)
X[:,11]=rng.binomial(1,0.85,n)
X[:,12]=rng.integers(0,24,n)
X[:,13]=rng.integers(0,6,n) # Mumbai context buckets
X[:,14]=rng.uniform(1,30,n)

# Synthetic label generator: intentionally transparent and documented, not real clinical data.
# Latent urgency rises with casualties, unconscious/critical patients, severe injury,
# fire, traffic/closure risk, long ETA, and low hospital capacity/availability.
z=(
  0.55*X[:,0] + 1.35*X[:,1] + 1.05*X[:,2] + 3.0*X[:,3] + 0.8*X[:,4] +
  0.45*X[:,5] + 0.55*X[:,6] + 1.15*X[:,7] + 0.08*X[:,8] +
  0.045*X[:,9] + (-1.2)*X[:,10] + (-0.7)*X[:,11] +
  0.015*np.abs(X[:,12]-14) + 0.05*X[:,13] + 0.07*X[:,14] + rng.normal(0,1.4,n)
)
# thresholds chosen to produce all three classes.
y=np.where(z<6.3,0,np.where(z<9.8,1,2)).astype(np.int64)
# ensure class balance if generator drifts
if len(np.unique(y))<3: raise RuntimeError('Synthetic generator failed to create 3 classes')

scaler=StandardScaler().fit(X)
Xs=scaler.transform(X)
clf=LogisticRegression(max_iter=2000,random_state=42,C=1.2)
clf.fit(Xs,y)

np.savez(MODEL_DIR/'emergency_risk_model.npz',
         mean=scaler.mean_.astype(np.float32), scale=scaler.scale_.astype(np.float32),
         coef=clf.coef_.astype(np.float32), intercept=clf.intercept_.astype(np.float32),
         classes=clf.classes_.astype(np.int64))

with open(DATA_DIR/'emergency_risk_training.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(FEATURES+['label'])
    for row,label in zip(X,y): w.writerow([float(v) if i not in (0,1,2,4,5,6,10,11,12,13) else int(v) for i,v in enumerate(row)]+[int(label)])
with open(AI/'model_metadata.json','w') as f:
    json.dump({'model':'multinomial_logistic_regression','features':FEATURES,'classes':{'0':'LOW','1':'HIGH','2':'CRITICAL'},'training_data':'synthetic simulation data; not clinical data','samples':int(n),'seed':20260930},f,indent=2)

# ---- Minimal ONNX ModelProto generator using dynamic protobuf descriptors ----
fd=descriptor_pb2.FileDescriptorProto(); fd.name='onnx_min.proto'; fd.package='onnx'; fd.syntax='proto3'
def msg(name, fields):
    m=fd.message_type.add(); m.name=name
    for num,nm,typ,label,type_name in fields:
        x=m.field.add(); x.number=num; x.name=nm; x.type=typ; x.label=label
        if type_name: x.type_name=type_name
    return m
# enum TensorProto.DataType values
# TensorProto: dims=1, data_type=2, float_data=4, int64_data=7, name=8, raw_data=9
msg('TensorProto',[(1,'dims',3,3,''),(2,'data_type',5,1,''),(4,'float_data',2,3,''),(7,'int64_data',3,3,''),(8,'name',9,1,''),(9,'raw_data',12,1,'')])
msg('TensorShapeProto_Dimension',[(1,'dim_value',3,1,''),(2,'dim_param',9,1,'')])
msg('TensorShapeProto',[(1,'dim',11,3,'.onnx.TensorShapeProto_Dimension')])
msg('TypeProto_Tensor',[(1,'elem_type',5,1,''),(2,'shape',11,1,'.onnx.TensorShapeProto')])
msg('TypeProto',[(1,'tensor_type',11,1,'.onnx.TypeProto_Tensor')])
msg('ValueInfoProto',[(1,'name',9,1,''),(2,'type',11,1,'.onnx.TypeProto')])
msg('NodeProto',[(1,'input',9,3,''),(2,'output',9,3,''),(3,'name',9,1,''),(4,'op_type',9,1,'')])
msg('GraphProto',[(1,'node',11,3,'.onnx.NodeProto'),(2,'name',9,1,''),(5,'initializer',11,3,'.onnx.TensorProto'),(11,'input',11,3,'.onnx.ValueInfoProto'),(12,'output',11,3,'.onnx.ValueInfoProto')])
msg('OperatorSetIdProto',[(1,'domain',9,1,''),(2,'version',3,1,'')])
msg('ModelProto',[(1,'ir_version',3,1,''),(2,'producer_name',9,1,''),(7,'graph',11,1,'.onnx.GraphProto'),(14,'opset_import',11,3,'.onnx.OperatorSetIdProto')])
pool=descriptor_pool.DescriptorPool(); pool.Add(fd)
def cls(name): return message_factory.GetMessageClass(pool.FindMessageTypeByName('onnx.'+name))
Model=cls('ModelProto'); Tensor=cls('TensorProto'); Node=cls('NodeProto'); VI=cls('ValueInfoProto')

def tensor(name,arr):
    arr=np.asarray(arr,dtype=np.float32)
    t=Tensor(name=name,data_type=1)
    t.dims.extend(list(arr.shape)); t.raw_data=arr.tobytes(); return t

def vi(name,shape):
    v=VI(name=name); v.type.tensor_type.elem_type=1
    for d in shape:
        dim=v.type.tensor_type.shape.dim.add()
        if isinstance(d,int): dim.dim_value=d
        else: dim.dim_param=d
    return v

# graph: X -> Sub(mean) -> Div(scale) -> MatMul(coef^T) -> Add(intercept) -> Softmax
G=cls('GraphProto')(name='ResQMeshEmergencyRisk')
G.input.extend([vi('features',['batch',len(FEATURES)])]); G.output.extend([vi('probabilities',['batch',3])])
G.initializer.extend([tensor('mean',scaler.mean_),tensor('scale',scaler.scale_),tensor('coef_T',clf.coef_.astype(np.float32).T),tensor('intercept',clf.intercept_)])
for name,ins,outs,op in [
 ('Normalize',['features','mean'],['x_centered'],'Sub'),
 ('Scale',['x_centered','scale'],['x_scaled'],'Div'),
 ('Linear',['x_scaled','coef_T'],['logits0'],'MatMul'),
 ('Bias',['logits0','intercept'],['logits'],'Add'),
 ('Probability',['logits'],['probabilities'],'Softmax')]:
    nnode=Node(name=name,op_type=op); nnode.input.extend(ins); nnode.output.extend(outs); G.node.append(nnode)
M=Model(ir_version=8,producer_name='ResQMesh AI')
M.graph.CopyFrom(G); ops=M.opset_import.add(); ops.domain=''; ops.version=13
(MODEL_DIR/'emergency_risk_model.onnx').write_bytes(M.SerializeToString())
print('created',MODEL_DIR/'emergency_risk_model.npz',MODEL_DIR/'emergency_risk_model.onnx')
print('classes',np.bincount(y), 'train acc',clf.score(Xs,y))
