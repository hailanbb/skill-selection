import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import {Store} from './store.js';
import {Engine} from './workflow.js';
import {readConfig,writeConfig,publicConfig} from './config.js';
import {Cloud,MoviePilot} from './clients.js';
import {exportJob,importScopes} from './reports.js';
import {home,digest,writable,errorText,cloudPath,within,localPath} from './util.js';
export const address=()=>process.platform==='win32'?'\\\\.\\pipe\\tvflow-'+digest(home()).slice(0,20):path.join(home(),'control.sock');
export async function rpc(method,params={}){return new Promise((resolve,reject)=>{const client=net.connect(address());client.setEncoding('utf8');let data='';client.setTimeout(180000);client.on('connect',()=>client.write(JSON.stringify({method,params})+'\n'));client.on('data',b=>{data+=b;if(data.length>32*1024*1024){client.destroy();reject(Error('响应过大'));return;}const at=data.indexOf('\n');if(at>=0){client.end();try{const r=JSON.parse(data.slice(0,at));r.ok?resolve(r.value):reject(Error(r.error));}catch(e){reject(e);}}});client.on('error',reject);client.on('timeout',()=>{client.destroy();reject(Error('后台响应超时；请重新查看任务状态，不重复执行'));});});}
export async function startDaemon(){
 fs.mkdirSync(home(),{recursive:true,mode:0o700});const lock=path.join(home(),'daemon.lock');
 if(fs.existsSync(lock)){const pid=Number(fs.readFileSync(lock,'utf8'));let alive=false;try{process.kill(pid,0);alive=true;}catch(e){if(e.code==='EPERM')alive=true;}if(alive)throw Error('后台已运行或锁对应进程仍在');fs.unlinkSync(lock);}
 fs.writeFileSync(lock,String(process.pid),{flag:'wx',mode:0o600});if(process.platform!=='win32'&&fs.existsSync(address()))fs.unlinkSync(address());
 const store=new Store(),engine=new Engine(store,readConfig);store.recover();let shutting=false;
 const dispatch=async(method,p)=>{
  const config=readConfig();
  if(method==='ping')return {version:'1.1.1',pid:process.pid};
  if(method==='config')return publicConfig(config);
  if(method==='set-config'){
   if(store.all('job').some(j=>['running','queued'].includes(j.status))&&['cloud','moviepilot','repair'].includes(p.section))throw Error('请先暂停任务，再修改连接或修复路径');
   const keys={root:['source','destination'],cloud:['url','token','transport'],moviepilot:['url','token','auth'],repair:['source','target'],outputs:['reports','records','logs']};
   if(!keys[p.section]?.includes(p.key)||typeof p.value!=='string')throw Error('配置字段无效');
   if(p.section==='outputs')p.value=writable(p.value);
   if(p.section==='root'){
    if(!p.value)throw Error('路径不能为空');const c=new Cloud(config);try{await c.list(cloudPath(p.value));}finally{c.close();}config[p.key]=p.value;
   }else config[p.section][p.key]=p.value;
   writeConfig(config);return publicConfig(config);
  }
  if(method==='browse'){const c=new Cloud(config);try{return await c.list(cloudPath(p.path));}finally{c.close();}}
  if(method==='jobs')return store.all('job').map(j=>({...j,results:undefined,config:undefined,payload:undefined}));
  if(method==='job'){const j=store.get('job',p.id);if(!j)throw Error('任务不存在');return j;}
  if(method==='workflows')return store.all('workflow').map(w=>({id:w.id,createdAt:w.createdAt,scopes:w.scopes,count:w.seasons.length}));
  if(method==='workflow')return engine.workflow(p.id);
  if(method==='plans')return store.all('plan').filter(x=>(!p.workflow||x.workflow===p.workflow)&&(!p.kind||x.kind===p.kind));
  if(method==='approve')return engine.approve(p.id,p.hash);
  if(method==='create')return engine.create(p.stage,p);
  if(method==='pause')return engine.pause(p.id);
  if(method==='resume')return engine.resume(p.id);
  if(method==='export'){const j=store.get('job',p.id);if(!j)throw Error('任务不存在');const r=exportJob(j,engine.workflow(j.workflow),store.all('plan').filter(x=>x.job===j.id||x.id===j.payload.plan));j.files=[...new Set([...j.files,...r.files])];j.exportErrors=r.errors;store.put('job',j.id,j);return r;}
  if(method==='import')return {scopes:importScopes(p.file,config),note:'仅导入检查范围；重新初检后才能补缺或归档，未导入外部操作指令'};
  if(method==='outputs-check')return Object.fromEntries(Object.entries(config.outputs).map(([k,v])=>[k,writable(v)]));
  if(method==='doctor'){
   const result={};let c;try{c=new Cloud(config);const rows=await c.list(config.source);result.cloud={ok:true,children:rows.length,transport:config.cloud.transport};}catch(e){result.cloud={ok:false,error:errorText(e)};}finally{c?.close();}
   try{const mp=new MoviePilot(config),active=await mp.active();if(!Array.isArray(active))throw Error('下载查询格式不兼容');result.moviepilot={ok:true,active:active.length};}catch(e){result.moviepilot={ok:false,error:errorText(e)};}
   result.outputs=Object.fromEntries(Object.entries(config.outputs).map(([k,v])=>{try{return [k,{ok:true,path:writable(v)}];}catch(e){return [k,{ok:false,error:errorText(e)}];}}));return result;
  }
  throw Error('未知控制命令');
 };
 const server=net.createServer(socket=>{socket.setEncoding('utf8');let data='',done=false;socket.setTimeout(190000,()=>socket.destroy());socket.on('error',()=>{});socket.on('data',async b=>{
  if(done)return;data+=b.toString('utf8');if(data.length>2*1024*1024){socket.destroy();return;}const at=data.indexOf('\n');if(at<0)return;done=true;
  try{const r=JSON.parse(data.slice(0,at));const value=await dispatch(r.method,r.params||{});socket.end(JSON.stringify({ok:true,value})+'\n');}catch(e){socket.end(JSON.stringify({ok:false,error:errorText(e)})+'\n');}
 });});
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(address(),resolve);});if(process.platform!=='win32')fs.chmodSync(address(),0o600);
 const tick=setInterval(()=>{if(shutting||engine.active)return;const j=store.all('job').reverse().find(j=>j.status==='queued');if(j)engine.run(j).catch(e=>{console.error(errorText(e));});},200);
 const shutdown=()=>{if(shutting)return;shutting=true;clearInterval(tick);if(engine.active)engine.pause(engine.active);const wait=setInterval(()=>{if(engine.active)return;clearInterval(wait);server.close(()=>{store.close();if(fs.existsSync(lock))fs.unlinkSync(lock);process.exit(0);});},100);wait.unref();setTimeout(()=>process.exit(1),70000).unref();};
 process.once('SIGTERM',shutdown);process.once('SIGINT',shutdown);return {server,store,engine};
}
