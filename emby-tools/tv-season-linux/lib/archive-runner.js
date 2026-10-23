import {parent,base,now,clone,fingerprint} from './util.js';
export async function inventory(cloud,p,depth=0,budget={count:0}){if(depth>10)throw Error('目录层级过深');const rows=await cloud.list(p);budget.count+=rows.length;if(budget.count>50000)throw Error('目录清单过大');const all=[...rows];for(const d of rows.filter(f=>f.directory))all.push(...await inventory(cloud,d.path,depth+1,budget));return all;}
const relocated=(f,from,to)=>({...f,path:to+f.path.slice(from.length)});
const equal=(a,b)=>fingerprint(a)===fingerprint(b);
function expect(condition,message){if(!condition)throw Error(message);}
async function absent(cloud,p){return !(await cloud.list(parent(p))).some(f=>f.path===p);}
async function unitFiles(cloud,op){const rows=await cloud.list(parent(op.target)),entry=rows.find(f=>f.path===op.target);if(!entry)return null;return [entry,...(entry.directory?await inventory(cloud,op.target):[])];}
function sourceUnit(plan,op){return plan.rawSource.filter(f=>f.path===op.source||f.path.startsWith(op.source+'/'));}
function compareMoved(a,b){
 // Cloud providers may assign a different ID on move. Compare content metadata, not IDs.
 return equal(a.map(f=>({...f,id:''})),b.map(f=>({...f,id:''})));
}
async function verifyUnit(plan,op,cloud){
 expect(await absent(cloud,op.source),'源移动单元仍存在，结果待核实');
 if(op.kind==='show'){const actual=await inventory(cloud,op.target),expected=plan.rawSource.map(f=>relocated(f,plan.source,plan.target));expect(compareMoved(expected,actual),'目标移动清单不一致');}
 else{const actual=await unitFiles(cloud,op);expect(actual&&compareMoved(sourceUnit(plan,op).map(f=>relocated(f,op.source,op.target)),actual),'目标移动单元属性不一致');}
}
async function fresh(plan,journal,cloud){
 const done=journal.operations.filter(o=>o.state==='verified');
 if(plan.mode==='show'){if(done.length)return;expect(equal(plan.rawSource,await inventory(cloud,plan.source)),'预览后源文件改变');expect(await absent(cloud,plan.target),'归档目标已经出现，停止');return;}
 const remaining=plan.rawSource.filter(f=>!done.some(o=>f.path===o.source||f.path.startsWith(o.source+'/')));
 expect(equal(remaining,await inventory(cloud,plan.source)),'源清单在移动期间改变');
 const original=await inventory(cloud,plan.target);const expected=[...plan.rawDestination,...done.flatMap(op=>sourceUnit(plan,op).map(f=>relocated(f,op.source,op.target)))];
 expect(compareMoved(expected,original),'目标原内容或已移入内容改变');
}
export async function runArchive(plan,{cloud,load,save,checkpoint,progress,noActive,core,verifyOnly=false}){
 let journal=load();
 if(!journal||journal.verified&&journal.id!==plan.id){if(verifyOnly)throw Error('没有匹配的可核实归档记录');journal={...clone(plan),rows:undefined,operations:clone(plan.operations),pending:false,incomplete:true,at:now(),history:journal?[journal]:[]};}
 if(journal.id!==plan.id)throw Error('存在另一份未闭环归档记录');
 // Read-only reconciliation can prove completion, but never retries an ambiguous request.
 for(const op of journal.operations.filter(o=>o.state==='pending')){await verifyUnit(plan,op,cloud);op.state='verified';op.finishedAt=now();save(journal);}
 if(journal.cleanup?.state==='pending'){
  if(await absent(cloud,plan.source)){const result=await core.verify(journal,p=>cloud.list(p));result.incomplete=false;save(result);return result;}
  throw Error('源目录清理结果不明，请先在CloudDrive2核实；不会重发删除');
 }
 journal.pending=false;save(journal);
 if(verifyOnly){
  if(journal.operations.some(o=>o.state!=='verified'))return {...journal,state:'已核实已发操作，仍有未执行项；可继续原任务'};
  try{const result=await core.verify(journal,p=>cloud.list(p));result.incomplete=false;save(result);return result;}catch{return {...journal,state:'移动已核实，源清理尚未执行；可继续原任务'};}
 }
 for(const op of journal.operations.filter(o=>o.state!=='verified')){
  checkpoint();await noActive();await fresh(plan,journal,cloud);checkpoint();progress('移动：'+op.source+' → '+op.target);
  op.state='pending';op.at=now();journal.pending=true;save(journal);
  await cloud.move(op);await verifyUnit(plan,op,cloud);op.state='verified';op.finishedAt=now();journal.pending=false;save(journal);
 }
 if(plan.mode==='seasons'){
  checkpoint();await noActive();await fresh(plan,journal,cloud);
  const discard=core.cleanupFiles(plan),actual=await cloud.list(plan.source);expect(core.equal(discard,actual),'源不只包含已确认共用资料');
  journal.cleanup={...plan.cleanup,state:'pending',at:now()};journal.pending=true;save(journal);
  if(actual.length)await cloud.remove(actual);
  expect(!(await cloud.list(plan.source)).length,'源目录出现新内容，停止删除');await cloud.removeSource(plan.source);
 }
 const result=await core.verify(journal,p=>cloud.list(p));result.incomplete=false;save(result);return result;
}
