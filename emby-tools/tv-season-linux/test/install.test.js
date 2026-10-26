import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {installForAccount,installLayout,quoteUnit} from '../scripts/install-user.js';

function fixture(t) {
 const dir=fs.mkdtempSync(path.join(process.env.TVFLOW_TEST_TMP||os.tmpdir(),'tvflow-install-'));
 const appDir=path.join(dir,'中文 程序'),entry=path.join(appDir,'bin/tvflow.js');
 fs.mkdirSync(path.dirname(entry),{recursive:true});fs.writeFileSync(entry,'#!/usr/bin/env node\n');
 // Windows非管理员不能创建文件符号链接；只替身链接原语，其余文件/冲突检查真实执行。
 // Ubuntu CI直接使用真实符号链接，不进行替身。
 if(process.platform==='win32'){
  const links=new Map(),lstat=fs.lstatSync,readlink=fs.readlinkSync;
  t.mock.method(fs,'symlinkSync',(target,link)=>{fs.writeFileSync(link,'link test double',{flag:'wx'});links.set(link,target);});
  t.mock.method(fs,'lstatSync',(...args)=>links.has(args[0])?{isSymbolicLink:()=>true,isFile:()=>false}:lstat(...args));
  t.mock.method(fs,'readlinkSync',(...args)=>links.has(args[0])?links.get(args[0]):readlink(...args));
 }
 return {dir,entry,options:{appDir,homeDir:path.join(dir,'account'),binDir:path.join(dir,'bin'),unitDir:path.join(dir,'units'),nodePath:'/opt/node/bin/node',stateDir:''},close(){if(process.platform==='win32')t.mock.restoreAll();fs.rmSync(dir,{recursive:true,force:true});}};
}

test('root安装到系统布局，固定root状态目录，不依赖用户服务或linger',t=>{
 assert.deepEqual(installLayout({system:true,homeDir:'/root'}),{binDir:'/usr/local/bin',unitDir:'/etc/systemd/system'});
 const f=fixture(t);try{
  const result=installForAccount({...f.options,system:true}),unit=fs.readFileSync(result.unit,'utf8');
  assert.equal(fs.readlinkSync(result.target),f.entry);assert.match(unit,/\nUser=root\n/);
  assert.match(unit,/WantedBy=multi-user.target\n/);assert.match(unit,/UMask=0077/);
  assert.ok(unit.includes(quoteUnit('HOME='+f.options.homeDir)));
  assert.ok(unit.includes(quoteUnit('TVFLOW_HOME='+result.data)));
  assert.ok(unit.includes(quoteUnit(f.entry,{exec:true})+' daemon'));
  assert.deepEqual(installForAccount({...f.options,system:true}),result);
 }finally{f.close();}
});

test('普通用户保留原命令和用户级服务，重复安装兼容既有配置',t=>{
 const homeDir='/home/media',layout=installLayout({system:false,homeDir});
 assert.equal(layout.binDir,path.join(homeDir,'.local/bin'));
 assert.equal(layout.unitDir,path.join(homeDir,'.config/systemd/user'));
 const f=fixture(t);try{
  const result=installForAccount({...f.options,system:false}),unit=fs.readFileSync(result.unit,'utf8');
  assert.match(unit,/WantedBy=default.target\n/);assert.ok(!unit.includes('User=root'));assert.ok(!unit.includes('Environment='));
  assert.deepEqual(installForAccount({...f.options,system:false}),result);
 }finally{f.close();}
});

test('不同的既有命令、服务或失效链接不被覆盖，不产生半成品',t=>{
 for(const collision of ['command','unit','dangling']){
  const f=fixture(t);try{
   const target=path.join(f.options.binDir,'tvflow'),unit=path.join(f.options.unitDir,'tvflow.service');
   if(collision==='unit'){fs.mkdirSync(f.options.unitDir);fs.writeFileSync(unit,'personal unit');}
   else{fs.mkdirSync(f.options.binDir);if(collision==='command')fs.writeFileSync(target,'personal command');else fs.symlinkSync(path.join(f.dir,'missing.js'),target);}
   assert.throws(()=>installForAccount({...f.options,system:true}),/未覆盖/);
   if(collision==='unit'){assert.equal(fs.readFileSync(unit,'utf8'),'personal unit');assert.ok(!fs.existsSync(target));}
   else{assert.ok(!fs.existsSync(unit));if(collision==='command')assert.equal(fs.readFileSync(target,'utf8'),'personal command');else assert.equal(fs.readlinkSync(target),path.join(f.dir,'missing.js'));}
  }finally{f.close();}
 }
});

test('服务路径转义保留中文、空格和特殊字符，拒绝控制字符',t=>{
 assert.equal(quoteUnit('/中文 a%/$x"b',{exec:true}),'"/中文 a%%/$$x\\"b"');
 assert.equal(quoteUnit('TVFLOW_HOME=/中文 a%/$x'),'"TVFLOW_HOME=/中文 a%%/$x"');
 for(const value of ['a\nb','a\rb','a\0b'])assert.throws(()=>quoteUnit(value),/控制字符/);
 const f=fixture(t);try{const custom=path.join(f.dir,'自定义 数据%$');const r=installForAccount({...f.options,system:true,stateDir:custom});assert.equal(r.data,custom);assert.ok(fs.readFileSync(r.unit,'utf8').includes(quoteUnit('TVFLOW_HOME='+custom)));}finally{f.close();}
});

test('专用Node通过独立包装命令启动，不依赖服务器全局Node或nvm',t=>{
 const f=fixture(t);try{
  const managed=path.join(f.dir,'independent-node/bin/node');fs.mkdirSync(path.dirname(managed),{recursive:true});fs.writeFileSync(managed,'runtime fixture');
  const r=installForAccount({...f.options,system:true,runtimeNode:managed}),command=fs.readFileSync(r.target,'utf8');
  assert.ok(command.includes('# tvflow-managed-command'));assert.ok(command.includes('# tvflow-app: '+f.options.appDir));assert.ok(command.includes('"$@"'));assert.ok(fs.readFileSync(r.unit,'utf8').includes(quoteUnit(managed,{exec:true})));
  assert.deepEqual(installForAccount({...f.options,system:true,runtimeNode:managed}),r);
 }finally{f.close();}
});
