import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {rpc} from '../lib/daemon.js';
import {Store} from '../lib/store.js';
import {sleep} from '../lib/util.js';
test('独立后台进程RPC、配置路径、客户断开后继续任务、重启恢复但不自动续跑',async()=>{
 const root=fs.mkdtempSync(path.join(process.env.TVFLOW_TEST_TMP||os.tmpdir(),'tvflow-daemon-')),previous=process.env.TVFLOW_ROOT;process.env.TVFLOW_ROOT=root;let child,stderr='';
 const launch=async()=>{child=spawn(process.execPath,['bin/tvflow.js','daemon'],{stdio:['ignore','pipe','pipe'],windowsHide:true,env:{...process.env,TVFLOW_ROOT:root}});child.stderr.on('data',b=>stderr+=b);for(let i=0;i<60;i++){try{await rpc('ping');return;}catch{}await sleep(100);}throw Error('daemon did not start '+stderr);};
 const stop=async()=>{if(child&&child.exitCode===null){const exited=once(child,'exit');child.kill('SIGTERM');await exited;}};
 try{await launch();const c=await rpc('config');assert.equal(c.source,'/115/Library_incs/nas');const reportDir=path.join(root,'reports/自定义报告');await rpc('set-config',{section:'outputs',key:'reports',value:reportDir});assert.equal((await rpc('config')).outputs.reports,reportDir);
  const outside=path.join(root,'不应创建');await assert.rejects(()=>rpc('set-config',{section:'outputs',key:'reports',value:outside}),/保存位置必须在/);assert.ok(!fs.existsSync(outside));
  const job=await rpc('create',{stage:'inspect',scopes:['/115/Library_incs/nas/动漫']});let result;for(let i=0;i<60;i++){result=await rpc('job',{id:job.id});if(result.status==='failed')break;await sleep(100);}assert.equal(result.status,'failed');assert.ok(result.files.some(p=>p.endsWith('.csv')));assert.ok(result.files.some(p=>p.endsWith('.xlsx')));
  await stop();const store=new Store(path.join(root,'data'));const stored=store.get('job',job.id);stored.status='running';store.put('job',job.id,stored);store.put('download','test',[{state:'uncertain'}]);store.close();await launch();assert.equal((await rpc('job',{id:job.id})).status,'paused');assert.equal((await rpc('config')).outputs.reports,reportDir);
 }finally{await stop();if(previous===undefined)delete process.env.TVFLOW_ROOT;else process.env.TVFLOW_ROOT=previous;fs.rmSync(root,{recursive:true,force:true});}
});
