import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {uninstallPlan,uninstall} from '../scripts/uninstall.js';
function setup(){
 const dir=fs.mkdtempSync(path.join(process.env.TVFLOW_TEST_TMP||os.tmpdir(),'tvflow-uninstall-')),app=path.join(dir,'app'),homeDir=path.join(dir,'home'),bin=path.join(dir,'tvflow'),unit=path.join(dir,'tvflow.service'),dataDir=path.join(homeDir,'.local/share/tvflow');
 fs.mkdirSync(path.join(app,'bin'),{recursive:true});fs.writeFileSync(path.join(app,'package.json'),JSON.stringify({name:'tv-season-linux'}));fs.writeFileSync(path.join(app,'bin/tvflow.js'),'// fixture');
 fs.writeFileSync(bin,'#!/bin/bash\n# tvflow-managed-command\n# tvflow-app: '+app+'\n');fs.writeFileSync(unit,'Description=TVFlow 剧集整理Linux版\nExecStart='+path.join(app,'bin/tvflow.js')+' daemon\n');
 fs.mkdirSync(dataDir,{recursive:true});fs.writeFileSync(path.join(dataDir,'config.json'),JSON.stringify({schema:1,cloud:{token:'PRIVATE'},moviepilot:{token:'PRIVATE'},outputs:{}}));
 const options={homeDir,defaultApp:app,binPaths:[bin],unitPaths:[unit],dataDir};
 return {dir,app,bin,unit,dataDir,options,close(){fs.rmSync(dir,{recursive:true,force:true});}};
}
test('卸载清除源码/命令/服务/本机状态，新安装的Node及其他程序保留',async()=>{
 const f=setup();try{const shared=path.join(f.dir,'shared-node');fs.writeFileSync(shared,'keep');const plan=uninstallPlan(f.options);assert.ok(!JSON.stringify(plan).includes('PRIVATE'));await uninstall(plan,{run:()=>{},findPids:()=>[]});for(const p of [f.app,f.bin,f.unit,f.dataDir])assert.equal(fs.existsSync(p),false);assert.equal(fs.readFileSync(shared,'utf8'),'keep');}finally{f.close();}
});
test('自定义报告目录只清除任务记录中的本程序文件，保留相邻无关文件',async()=>{
 const f=setup();try{const root=path.join(f.dir,'shared-reports'),id='J0123456789',folder=path.join(root,id);fs.mkdirSync(folder,{recursive:true});const own=path.join(folder,'inspect_'+id+'_report.xlsx'),other=path.join(folder,'私人文件.txt');fs.writeFileSync(own,'report');fs.writeFileSync(other,'keep');const db=new DatabaseSync(path.join(f.dataDir,'state.sqlite'));db.exec('CREATE TABLE records(kind TEXT,key TEXT,value TEXT)');db.prepare('INSERT INTO records VALUES(?,?,?)').run('job',id,JSON.stringify({id,stage:'inspect',files:[own,other],config:{outputs:{reports:root}}}));db.close();const p=uninstallPlan(f.options);assert.deepEqual(p.files,[own]);await uninstall(p,{run:()=>{},findPids:()=>[]});assert.ok(!fs.existsSync(own));assert.equal(fs.readFileSync(other,'utf8'),'keep');}finally{f.close();}
});
test('未识别的同名服务或命令不删除；后台未退出时拒绝继续清理',async()=>{
 const f=setup();try{fs.writeFileSync(f.bin,'other tool');fs.writeFileSync(f.unit,'other service');const p=uninstallPlan(f.options);assert.equal(p.commands.length,0);assert.equal(p.units.length,0);assert.equal(p.warnings.length,2);await assert.rejects(()=>uninstall(p,{run:()=>{},findPids:()=>[123],signal:()=>{},timeoutMs:0}),/后台尚未退出/);assert.ok(fs.existsSync(f.app));assert.ok(fs.existsSync(f.dataDir));}finally{f.close();}
});
test('无法确认归属的数据目录保留；危险公共路径不能加入递归清理清单',()=>{
 const f=setup();try{fs.unlinkSync(path.join(f.dataDir,'config.json'));fs.writeFileSync(path.join(f.dataDir,'personal.txt'),'keep');const p=uninstallPlan(f.options);assert.equal(p.dataDirs.length,0);assert.ok(p.warnings.length);if(process.platform==='linux')for(const dir of ['/','/home','/root','/usr/local'])assert.throws(()=>uninstallPlan({...f.options,dataDir:dir}),/拒绝清理公共目录/);}finally{f.close();}
});
