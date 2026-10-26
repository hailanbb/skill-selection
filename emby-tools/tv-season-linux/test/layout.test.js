import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {layout} from '../lib/layout.js';
import {defaults,readConfig,writeConfig,validate} from '../lib/config.js';

test('默认按程序位置集中存储，不再依赖登录账户的家目录',()=>{
 const root=path.resolve(fileURLToPath(new URL('..',import.meta.url))),l=layout({HOME:'/root',TVFLOW_HOME:'/旧位置'});
 assert.equal(l.root,root);assert.equal(l.config,path.join(root,'config/config.json'));assert.equal(l.data,path.join(root,'data'));
 for(const k of ['reports','records','logs'])assert.equal(l.outputs[k],path.join(root,k));
 assert.equal(l.daemonLog,path.join(root,'logs/daemon-start.log'));
});

test('配置往返保留中文、配置和默认输出集中，外部或跨角色保存路径被拒绝',()=>{
 const root=fs.mkdtempSync(path.join(process.env.TVFLOW_TEST_TMP||os.tmpdir(),'tvflow-layout-')),previous=process.env.TVFLOW_ROOT;process.env.TVFLOW_ROOT=root;
 try{
  const c=defaults();c.source='/115/电视剧/韩国剧集';c.outputs.reports=path.join(root,'reports/日常检查');writeConfig(c);
  const saved=readConfig();assert.equal(saved.source,c.source);assert.deepEqual(saved.outputs,c.outputs);
  assert.ok(fs.existsSync(path.join(root,'config/config.json')));assert.ok(!fs.existsSync(path.join(root,'data/config.json')));
  for(const value of [path.join(root,'外部'),path.join(root,'logs'),path.join(root,'reports/../data'),path.join(root,'reports-other')]){
   const bad=defaults();bad.outputs.reports=value;assert.throws(()=>validate(bad),/保存位置必须在/);
  }
  if(process.platform!=='win32')assert.equal(fs.statSync(path.join(root,'config/config.json')).mode&0o777,0o600);
 }finally{if(previous===undefined)delete process.env.TVFLOW_ROOT;else process.env.TVFLOW_ROOT=previous;fs.rmSync(root,{recursive:true,force:true});}
});
