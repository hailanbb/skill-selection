import grpc from '@grpc/grpc-js';
import loader from '@grpc/proto-loader';
import {fileURLToPath} from 'node:url';
import {cloudPath,parent,within,fingerprint,sleep,now,digest} from './util.js';
import {I,D} from './cores.js';
const proto=fileURLToPath(new URL('../vendor/clouddrive.proto',import.meta.url));
const definition=loader.loadSync(proto,{keepCase:true,longs:String,enums:String,defaults:false,oneofs:true});
const service=definition['clouddrive.CloudDriveFileSrv'];
const Service=grpc.loadPackageDefinition(definition).clouddrive.CloudDriveFileSrv;
export function decodeFrames(buffer,method){
 const messages=[];let offset=0,status=null;
 while(offset<buffer.length){if(offset+5>buffer.length)throw Error('gRPC-Web帧头不完整');const flag=buffer[offset],len=buffer.readUInt32BE(offset+1);offset+=5;if(len>64*1024*1024||offset+len>buffer.length)throw Error('gRPC-Web帧不完整或过大');const body=buffer.subarray(offset,offset+len);offset+=len;
  if(flag===128){const text=body.toString('utf8');const match=/(?:^|\r?\n)grpc-status:\s*(\d+)/i.exec(text);if(!match)throw Error('gRPC-Web缺少最终状态');status=Number(match[1]);}
  else if(flag===0){if(status!==null)throw Error('gRPC-Web结束后出现数据');messages.push(method.responseDeserialize(body));}
  else throw Error('不支持压缩gRPC-Web帧');
 }
 if(status!==0)throw Error('CloudDrive2请求未完整成功：gRPC '+(status??'缺少最终状态'));
 return messages;
}
export function normalizeFile(f,folder){
 const p=cloudPath(f.fullPathName),name=f.name;
 if(parent(p)!==folder||typeof name!=='string'||p!==folder.replace(/\/$/,'')+'/'+name||/[\/\\\x00-\x1f]/.test(name))throw Error('CloudDrive2列表路径不一致');
 const dir=f.isDirectory===true||f.fileType==='Directory',seconds=f.writeTime?.seconds,nanos=f.writeTime?.nanos||0;
 const date=seconds===undefined?null:new Date(Number(seconds)*1000+Math.floor(nanos/1e6));
 const modified=date&&Number.isFinite(+date)?new Date(+date+8*3600000).toISOString().slice(0,19).replace('T',' '):'';
 const bytes=f.size===undefined?'':String(f.size);if(bytes&&!/^\d+$/.test(bytes))throw Error('CloudDrive2大小格式不正确');
 return {path:p,name,directory:dir,id:String(f.id||''),bytes,size:bytes?bytes+' B':'',modified,rawTime:seconds===undefined?'':seconds+':'+nanos};
}
export class Cloud{
 constructor(config){this.config=config;this.origin=config.cloud.url;if(!this.origin||!config.cloud.token)throw Error('请先设置CloudDrive2连接和认证');const url=new URL(this.origin);this.client=new Service(url.host,url.protocol==='https:'?grpc.credentials.createSsl():grpc.credentials.createInsecure(),{'grpc.max_receive_message_length':64*1024*1024});}
 async rpc(name,request,stream=false){
  const m=service[name];if(!m)throw Error('协议不支持 '+name);
  if(this.config.cloud.transport==='grpc-web'){
   const payload=m.requestSerialize(request),body=Buffer.alloc(payload.length+5);body.writeUInt32BE(payload.length,1);payload.copy(body,5);
   let response;try{response=await fetch(this.origin+m.path,{method:'POST',redirect:'error',headers:{'content-type':'application/grpc-web+proto','x-grpc-web':'1',authorization:'Bearer '+this.config.cloud.token},body,signal:AbortSignal.timeout(60000)});}catch{throw Error('CloudDrive2网络请求失败或超时，结果可能不明');}
   if(!response.ok)throw Error('CloudDrive2 HTTP '+response.status);
   const chunks=[];let size=0;for await(const c of response.body){size+=c.length;if(size>64*1024*1024)throw Error('CloudDrive2响应过大');chunks.push(c);}
   const values=decodeFrames(Buffer.concat(chunks),m);if(!stream&&values.length!==1)throw Error('CloudDrive2响应数量异常');return stream?values:values[0];
  }
  const metadata=new grpc.Metadata();metadata.set('authorization','Bearer '+this.config.cloud.token);
  return new Promise((resolve,reject)=>{
   const options={deadline:Date.now()+60000};const failed=e=>reject(Error('CloudDrive2请求失败：gRPC '+e.code+'；未确认操作结果'));
   if(!stream){this.client[name](request,metadata,options,(e,r)=>e?failed(e):resolve(r));return;}
   const values=[];let count=0,ended=false;const call=this.client[name](request,metadata,options);
   call.on('data',r=>{count+=(r.subFiles||[]).length;if(count>100000){call.cancel();return;}values.push(r);});call.on('error',failed);call.on('end',()=>{ended=true;});call.on('status',s=>{if(s.code===0&&ended)resolve(values);else if(s.code===0)setImmediate(()=>ended?resolve(values):reject(Error('CloudDrive2目录流未完整结束')));});
  });
 }
 async list(p){p=cloudPath(p);const replies=await this.rpc('GetSubFiles',{path:p,forceRefresh:true,checkExpires:true},true);const rows=replies.flatMap(r=>(r.subFiles||[]).map(f=>normalizeFile(f,p)));if(new Set(rows.map(r=>r.path)).size!==rows.length)throw Error('CloudDrive2返回重复路径');return rows;}
 guard(p){p=cloudPath(p);if(!within(p,this.config.source)||p===this.config.source)throw Error('写操作超出源目录');return p;}
 async remove(files){if(!files.length||files.length>50)throw Error('删除批次必须为1—50个文件');files.forEach(f=>this.guard(f.path));const r=await this.rpc('DeleteFiles',{path:files.map(f=>f.path)});if(r.success!==true)throw Error('CloudDrive2未确认删除成功');}
 async move(op){this.guard(op.source);if(!this.config.destination||!within(op.target,this.config.destination))throw Error('移动目标越界');const r=await this.rpc('MoveFile',{theFilePaths:[op.source],destPath:parent(op.target),conflictPolicy:'Skip',handleConflictRecursively:false,moveAcrossClouds:false});if(r.success!==true)throw Error('CloudDrive2未确认移动成功');}
 async removeSource(p){this.guard(p);const r=await this.rpc('DeleteFile',{path:p,forceRefresh:true});if(r.success!==true)throw Error('CloudDrive2未确认源目录删除成功');}
 close(){this.client.close();}
}
export class MoviePilot{
 constructor(config){this.c=config.moviepilot;if(!this.c.url||!this.c.token)throw Error('请先设置MoviePilot连接和认证');this.defaults={baseURL:this.c.url+'/api/v1/'};}
 async call(method,route,{params={},body,timeout=180000}={}){
  if(!/^[a-z0-9_/-]+(?:%[0-9A-Fa-f]{2}[a-z0-9_%-]*)*$/i.test(route)&&!/^search\/media\//.test(route)&&!/^media\//.test(route))throw Error('API路径无效');
  if(route.includes('..')||route.includes('?')||route.includes('#'))throw Error('API路径无效');
  const u=new URL(route,this.defaults.baseURL);if(u.origin!==this.c.url||!u.pathname.startsWith('/api/v1/'))throw Error('拒绝跨域接口');for(const [k,v] of Object.entries(params))if(v!==null&&v!==undefined)u.searchParams.set(k,String(v));
  const headers={'content-type':'application/json'};headers[this.c.auth==='apikey'?'X-API-KEY':'Authorization']=this.c.auth==='apikey'?this.c.token:'Bearer '+this.c.token;
  let r;try{r=await fetch(u,{method,redirect:'error',headers,body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(timeout)});}catch{throw Error('MoviePilot网络请求失败或超时；写操作结果需核实');}
  if(!r.ok)throw Error('MoviePilot HTTP '+r.status+(r.status===401||r.status===403?'：认证或权限失败':''));
  const text=await r.text();if(text.length>32*1024*1024)throw Error('MoviePilot响应过大');try{return JSON.parse(text);}catch{throw Error('MoviePilot响应不是有效JSON');}
 }
 get(p,o={}){return this.call('GET',p,o);}post(p,b,o={}){return this.call('POST',p,{...o,body:b});}delete(p,o={}){return this.call('DELETE',p,{...o,body:o.data});}
 active(){return this.get('download/',{timeout:30000});}
}
export class Metadata{
 constructor(mp,store,checkpoint=()=>{},progress=()=>{}){this.mp=mp;this.store=store;this.checkpoint=checkpoint;this.progress=progress;}
 async tmdb(show,season){
  if(!/^\d+$/.test(show.tmdb))throw Error('目录没有有效TMDB ID');
  const m=await this.mp.get('media/'+encodeURIComponent('tmdb:'+show.tmdb),{params:{type_name:'电视剧'},timeout:30000});this.checkpoint();
  if(String(m.tmdb_id)!==show.tmdb)throw Error('MoviePilot返回的TMDB身份不一致');
  const episodes=await this.mp.get('tmdb/'+show.tmdb+'/'+season,{timeout:30000});if(!Array.isArray(episodes))throw Error('TMDB集目格式不支持');
  const summaries=Array.isArray(m.season_info)?m.season_info:[];
  const summary=summaries.find(s=>s.season_number===season)||((m.seasons?.[season] instanceof Array)?{season_number:season,episode_count:m.seasons[season].length}:null);
  if(!summary)throw Error('MoviePilot没有返回可校验的本季登记数量');
  const checked=episodes.map(e=>{const d=e.air_date;const valid=/^\d{4}-\d{2}-\d{2}$/.test(d||'')&&Number.isFinite(Date.parse(d+'T00:00:00Z'))&&new Date(d+'T00:00:00Z').toISOString().slice(0,10)===d;return {...e,air_date:valid?d:null};});
  return I.parseTmdbSeason({id:m.tmdb_id,name:m.title,status:m.status,seasons:[summary]},{season_number:season,episodes:checked},show,season,now());
 }
 async douban(show,season,bound=''){
  const key=digest([this.mp.c.url,show,season,bound]),hit=this.store.get('metadata',key);if(hit&&hit.expires>Date.now())return {...hit.value,fromCache:true};
  const policyKey=digest([this.mp.c.url,'douban']);const old=this.store.get('metadata-policy',policyKey,{});if(old.holdUntil>Date.now())throw Error('豆瓣来源访问受限，稍后重新检查');
  const request=async(route,params={})=>{
   while(true){this.checkpoint();const st=this.store.get('metadata-policy',policyKey,{}),wait=(st.last||0)+45000-Date.now();if(wait<=0)break;this.progress('等待豆瓣查询间隔，约 '+Math.ceil(wait/1000)+' 秒');await sleep(Math.min(wait,1000));}
   this.store.put('metadata-policy',policyKey,{last:Date.now()});
   try{return await this.mp.get(route,{params,timeout:30000});}catch(e){if(/429|403/.test(e.message))this.store.put('metadata-policy',policyKey,{last:Date.now(),holdUntil:Date.now()+1800000});throw e;}
  };
  let candidates=[];
  if(bound){const u=I.validSubjectUrl(bound);if(!u)throw Error('历史豆瓣链接不合法');candidates=[{douban_id:u.split('/')[4]}];}
  else{
   const seen=new Set();for(let page=1;page<=10;page++){
    const rows=await request('media/search',{title:show.title+(season>1?' 第'+season+'季':''),type:'media',source:'douban',page,count:20});if(!Array.isArray(rows))throw Error('豆瓣搜索响应不完整');
    if(!rows.length)break;for(const row of rows){const key=String(row.douban_id||'');if(!key)continue;if(seen.has(key))throw Error('豆瓣搜索分页重复，无法确认候选完整');seen.add(key);candidates.push(row);}if(rows.length<20)break;if(page===10)throw Error('豆瓣候选超过上限');
   }
   candidates=candidates.filter(m=>['电视剧','tv','TV'].includes(m.type)&&I.candidateMatches({title:m.title,aliases:m.names||[],releaseYears:[String(m.year||'')],tv:true},show,season,{inspectDetails:true}));
  }
  if(candidates.length!==1)throw Error('豆瓣候选不唯一或没有匹配条目，暂缓本季');
  const dbid=String(candidates[0].douban_id);if(!/^\d+$/.test(dbid))throw Error('豆瓣ID无效');
  const m=await request('douban/'+dbid);this.checkpoint();
  const detail={title:m.title,aliases:Array.isArray(m.names)?m.names:[],releaseYears:[String(m.year||'')],tv:['电视剧','tv','TV'].includes(m.type)};
  if(String(m.douban_id)!==dbid||!I.candidateMatches(detail,show,season))throw Error('豆瓣详情身份、年份或季号不匹配');
  if(m.season!=null&&Number(m.season)!==season)throw Error('豆瓣返回季号与本季冲突');
  const eps=m.seasons?.[season];if(eps!==undefined&&(!Array.isArray(eps)||!eps.length||!eps.every((e,i)=>e===i+1)))throw Error('豆瓣分季集目不完整');
  if(!eps&&Number(m.number_of_seasons)>1)throw Error('豆瓣仅返回多季总数，不能用作本季数量');
  const total=eps?eps.length:Number(m.number_of_episodes);
  if(!Number.isInteger(total)||total<1||total>10000)throw Error('豆瓣本季集数未确认');
  if(season>1&&I.titleIdentity(m.title).season!==season)throw Error('豆瓣详情未明确本季身份');
  // Unified MediaInfo.status is not proof that Douban explicitly says this season ended.
  const result={...detail,total,url:'https://movie.douban.com/subject/'+dbid+'/',checkedAt:now(),source:'douban',broadcast:'未确认',broadcastEvidence:'豆瓣集数经MoviePilot取得；未返回可验证的本季完结证据',channel:'MoviePilot'};
  this.store.put('metadata',key,{expires:Date.now()+86400000,value:result});return result;
 }
 async inspect(show,season,files){let primary;try{primary=await this.tmdb(show,season);}catch(e){if(e.name==='Pause')throw e;primary=null;}
  if(!primary){const db=await this.douban(show,season);return {db,audit:I.auditSource(files,season,db)};}
  return I.reviewIncomplete(files,season,primary,async()=>{try{return await this.douban(show,season);}catch(e){if(e.name==='Pause')throw e;return {error:e.message,deferred:true};}});
 }
}
