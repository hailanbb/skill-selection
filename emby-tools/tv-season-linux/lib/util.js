import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
export const now=()=>new Date().toISOString();
export const id=p=>p+crypto.randomBytes(5).toString('hex');
export const digest=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
export const clone=x=>structuredClone(x);
export const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export function cloudPath(p){
 if(typeof p!=='string'||!p.startsWith('/')||p.includes('//')||/[\\\x00-\x1f\x7f]/.test(p)||p.split('/').some(x=>x==='.'||x==='..'))throw Error('云盘路径必须为有效绝对路径');
 return p==='/'?p:p.replace(/\/$/,'');
}
export const parent=p=>path.posix.dirname(p);
export const base=p=>path.posix.basename(p);
export const within=(p,r)=>p===r||(r==='/'?p.startsWith('/'):p.startsWith(r+'/'));
export function independent(a,b){a=cloudPath(a);b=cloudPath(b);if(a==='/'||b==='/'||within(a,b)||within(b,a))throw Error('源与归档目录须独立，不能相同、嵌套或为云盘根');}
export const home=()=>path.resolve(process.env.TVFLOW_HOME||path.join(os.homedir(),'.local/share/tvflow'));
export function localPath(p){if(p==='~')p=os.homedir();else if(p.startsWith('~/'))p=path.join(os.homedir(),p.slice(2));if(!path.isAbsolute(p))throw Error('请输入Ubuntu本机绝对路径');return path.resolve(p);}
export function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});const tmp=file+'.'+id('tmp');const fd=fs.openSync(tmp,'wx',0o600);try{fs.writeFileSync(fd,value);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(tmp,file);}
export function writable(p){p=localPath(p);fs.mkdirSync(p,{recursive:true,mode:0o700});const f=path.join(p,id('.probe-'));fs.writeFileSync(f,'',{flag:'wx',mode:0o600});fs.unlinkSync(f);return p;}
export function safeText(x){return String(x??'').replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g,'');}
export function errorText(e){return safeText(e?.message||e).replace(/(Bearer\s+)[^\s]+/gi,'$1[已隐藏]').replace(/([?&](?:token|apikey|api_key|password)=)[^&\s]+/gi,'$1[已隐藏]').slice(0,2000);}
export function fingerprint(rows,{directories=false}={}){return digest(rows.map(f=>[f.path,f.name,!!f.directory,f.directory?'':String(f.bytes??f.size),f.directory&&!directories?'':String(f.rawTime??f.modified),f.id||'']).sort((a,b)=>a[0].localeCompare(b[0])));}
export function assertSame(a,b){if(fingerprint(a)!==fingerprint(b))throw Error('文件清单已变化，请重新检查');}
export function endpoint(s){const u=new URL(s);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash||u.pathname!=='/')throw Error('服务地址仅填写协议、主机和端口');return u.origin;}
export class Pause extends Error{constructor(){super('已暂停；已保存当前进度');this.name='Pause';}}
