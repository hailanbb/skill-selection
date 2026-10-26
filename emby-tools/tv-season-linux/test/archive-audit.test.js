import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import X from 'xlsx-js-style';
import {fixture,inspect} from './helpers.js';
import {digest} from '../lib/util.js';
async function archived(f){const first=await inspect(f);await f.engine.run(f.engine.create('archive',{workflow:first.workflow}));const p=f.store.all('plan')[0];f.engine.approve(p.id,p.hash);const j=f.engine.create('execute',{workflow:first.workflow,plan:p.id});await f.engine.run(j);return {first,p,j:f.store.get('job',j.id)};}
test('归档后自动对照季路径/集号/视频数/文件属性，Excel回读数据一致才输出',async()=>{
 const f=fixture();try{const {first,p,j}=await archived(f);assert.equal(j.status,'completed',JSON.stringify(j.errors));assert.equal(j.exportErrors.length,0,JSON.stringify(j.exportErrors));
  const s=f.engine.workflow(first.workflow).seasons[0];assert.equal(s.color,'archived');assert.equal(s.archiveAudit.ok,true);assert.equal(s.archiveAudit.actualEpisodes,2);assert.equal(s.archiveAudit.targetPath,p.body.target+'/Season 1');
  const book=X.read(fs.readFileSync(j.files.find(p=>p.endsWith('.xlsx'))),{type:'buffer'}),row=X.utils.sheet_to_json(book.Sheets['作品结果'])[0];assert.equal(row['季目录'],p.body.target+'/Season 1');assert.equal(row['归档源季目录'],f.season);assert.equal(row['归档核验结果'],'报告与云盘一致');assert.ok(book.Sheets['归档文件核验']);
 }finally{f.close();}
});
test('已归档的目标缺集/大小变化/源目录重现，手动只读复核标红并导出差异',async()=>{
 for(const change of ['missing','size','source','modified','extra']){const f=fixture();try{
  const {first,p}=await archived(f),target=p.body.target+'/Season 1';
  if(change==='missing')f.tree.get(target).pop();if(change==='size')f.tree.get(target)[0].bytes='999';if(change==='source')f.tree.get(f.config.source+'/动漫/日本动漫').push(f.file(f.config.source+'/动漫/日本动漫',f.name,true));
  if(change==='modified')f.tree.get(target)[0].modified='2026-10-26 10:00:00';if(change==='extra')f.tree.get(target).push(f.file(target,'未知文件.txt'));
  const writes=f.calls.length,j=f.engine.create('archive-audit',{workflow:first.workflow});await f.engine.run(j);assert.equal(f.calls.length,writes);assert.equal(f.store.get('job',j.id).status,'completed-with-issues');const s=f.engine.workflow(first.workflow).seasons[0];assert.equal(s.color,'red');assert.equal(s.archiveAudit.ok,false);assert.ok(s.archiveAudit.differences.length);assert.equal(f.store.get('archive',digest([f.config.cloud.url,f.show])).reportAudit.ok,false);
 }finally{f.close();}}
});
test('报告集数被改错，即使目标文件齐全也不能继续标紫',async()=>{
 const f=fixture();try{const {first}=await archived(f),w=f.engine.workflow(first.workflow);w.seasons[0].current=9;f.store.put('workflow',w.id,w);const j=f.engine.create('archive-audit',{workflow:w.id});await f.engine.run(j);assert.equal(f.engine.workflow(w.id).seasons[0].color,'red');assert.ok(f.engine.workflow(w.id).seasons[0].note.includes('已识别集数不一致'));}finally{f.close();}
});
test('归档物理操作已完成但报告核验被暂停，继续时不得重复移动或清理',async()=>{
 const f=fixture();try{const first=await inspect(f);await f.engine.run(f.engine.create('archive',{workflow:first.workflow}));const p=f.store.all('plan')[0];f.engine.approve(p.id,p.hash);const old=f.engine.auditPlan.bind(f.engine);let once=true;f.engine.auditPlan=async(ctx,...args)=>{if(once){once=false;f.engine.pause(ctx.j.id);f.engine.checkpoint(ctx.j);}return old(ctx,...args);};const j=f.engine.create('execute',{workflow:first.workflow,plan:p.id});await f.engine.run(j);assert.equal(f.store.get('job',j.id).status,'paused');const writes=f.calls.length;await f.engine.run(f.engine.resume(j.id));assert.equal(f.store.get('job',j.id).status,'completed');assert.equal(f.calls.length,writes);assert.equal(f.engine.workflow(first.workflow).seasons[0].archiveAudit.ok,true);}finally{f.close();}
});
