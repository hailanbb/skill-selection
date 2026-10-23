const grpc=require('@grpc/grpc-js'),loader=require('@grpc/proto-loader'),path=require('node:path');
const {C}=require('./cores.cjs');
function cloudPath(p){if(typeof p!=='string'||!p.startsWith('/')||p!=='/'&&p.endsWith('/')||p.includes('//')||/[\\\x00-\x1f]/.test(p)||p.split('/').some(s=>s==='.'||s==='..'))throw Error('Invalid CloudDrive path');return p;}
async function json(url,options={}){let r;try{r=await fetch(url,{...options,redirect:'error',signal:AbortSignal.timeout(180000)});}catch{throw Error('Remote request failed or timed out');}if(!r.ok)throw Error('Remote HTTP '+r.status);try{return await r.json();}catch{throw Error('Remote response is not JSON');}}
class MoviePilot{
 constructor(origin,token,mode='apikey'){this.origin=new URL(origin).origin;this.token=token;this.mode=mode;this.defaults={baseURL:this.origin+'/api/v1/'};}
 async call(method,endpoint,data,options={}){const u=new URL('/api/v1/'+endpoint,this.origin);for(const [k,v] of Object.entries(options.params||{}))u.searchParams.set(k,v);const headers={'Content-Type':'application/json'};if(this.mode==='bearer')headers.Authorization='Bearer '+this.token;else if(this.mode==='token')u.searchParams.set('token',this.token);else headers['X-API-KEY']=this.token;return json(u,{method,headers,...(data!==undefined?{body:JSON.stringify(data)}:{})});}
 get(p,o){return this.call('GET',p,undefined,o);}post(p,d,o){return this.call('POST',p,d,o);}delete(p,o){return this.call('DELETE',p,o?.data,o);}
}
class TMDB{
 constructor(key,language='zh-CN'){this.key=key;this.language=language;}
 get(p){if(!/^\/tv\/\d+(\/season\/\d+)?$/.test(p))throw Error('Invalid TMDB path');const u=new URL('https://api.themoviedb.org/3'+p);u.searchParams.set('api_key',this.key);u.searchParams.set('language',this.language);return json(u);}
 async season(id,n,name){const series=await this.get('/tv/'+id),season=await this.get('/tv/'+id+'/season/'+n);return C.parseTmdbSeason(series,season,{tmdb:String(id),title:name},n,new Date().toISOString());}
}
class CloudDrive{
 constructor(origin,token,transport=process.env.CD_TRANSPORT||'grpc-web'){this.origin=origin;this.token=token;this.transport=transport;const u=new URL(origin);if(!['https:','http:'].includes(u.protocol)||u.pathname!=='/')throw Error('CloudDrive origin must have no path');const def=loader.loadSync(path.join(__dirname,'../reference/clouddrive.proto'),{keepCase:true,longs:String,enums:String,defaults:true,oneofs:true});const proto=grpc.loadPackageDefinition(def);this.definition=proto.clouddrive.CloudDriveFileSrv.service;this.client=new proto.clouddrive.CloudDriveFileSrv(u.host,u.protocol==='https:'?grpc.credentials.createSsl():grpc.credentials.createInsecure());this.meta=new grpc.Metadata();this.meta.set('authorization','Bearer '+token);}
 unary(method,payload){if(this.transport==='grpc-web')return require('./grpc-web.cjs')(this.origin,this.token,this.definition[method],payload).then(rows=>{if(rows.length!==1)throw Error('Invalid unary RPC reply');return rows[0];});return new Promise((resolve,reject)=>this.client[method](payload,this.meta,{deadline:Date.now()+60000},(e,r)=>e?reject(Error('CloudDrive RPC '+method+' failed, code '+e.code)):resolve(r)));}
 async list(p){cloudPath(p);const rows=this.transport==='grpc-web'?(await require('./grpc-web.cjs')(this.origin,this.token,this.definition.GetSubFiles,{path:p,forceRefresh:true})).flatMap(r=>r.subFiles):await new Promise((resolve,reject)=>{const out=[];const call=this.client.GetSubFiles({path:p,forceRefresh:true},this.meta,{deadline:Date.now()+60000});call.on('data',r=>out.push(...r.subFiles));call.on('error',e=>reject(Error('CloudDrive listing failed, code '+e.code)));call.on('end',()=>resolve(out));});const result=rows.map(f=>({path:f.fullPathName,name:f.name,directory:f.isDirectory||f.fileType==='Directory',size:f.size+' B',modified:f.writeTime?new Date(Number(f.writeTime.seconds)*1000+Number(f.writeTime.nanos)/1e6).toISOString():''}));C.validateListing(result,p==='/'?'':p,result.length,{emptyConfirmed:true});return result;}
 async move(op){cloudPath(op.source);cloudPath(op.target);const r=await this.unary('MoveFile',{theFilePaths:[op.source],destPath:C.parent(op.target),conflictPolicy:'Skip',moveAcrossClouds:false,handleConflictRecursively:false});if(!r.success)throw Error('CloudDrive move rejected');}
 async remove(p){cloudPath(p);const r=await this.unary('DeleteFile',{path:p});if(!r.success)throw Error('CloudDrive delete rejected');}
 close(){this.client.close();}
}
module.exports={MoviePilot,TMDB,CloudDrive,cloudPath,json};
