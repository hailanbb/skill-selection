import fs from 'node:fs';
import path from 'node:path';
import {home,atomic,cloudPath,independent,localPath,endpoint} from './util.js';
export function defaults(){return {schema:1,source:'/115/Library_incs/nas',destination:'',cloud:{url:'',transport:'grpc',token:''},moviepilot:{url:'',auth:'apikey',token:''},repair:{source:'',target:''},outputs:{reports:path.join(home(),'reports'),records:path.join(home(),'records'),logs:path.join(home(),'logs')},sourceGapMs:45000};}
export function readConfig(){const f=path.join(home(),'config.json');if(!fs.existsSync(f))return defaults();const c=JSON.parse(fs.readFileSync(f,'utf8'));return validate(c);}
export function validate(c){
 if(c.schema!==1)throw Error('配置版本不支持');c.source=cloudPath(c.source);if(c.source==='/')throw Error('源根不能是云盘根目录');
 if(c.destination){c.destination=cloudPath(c.destination);independent(c.source,c.destination);}
 for(const k of ['cloud','moviepilot']){if(c[k].url)c[k].url=endpoint(c[k].url);if(typeof c[k].token!=='string'||/[\r\n]/.test(c[k].token))throw Error('认证字段无效');}
 if(!['grpc','grpc-web'].includes(c.cloud.transport)||!['apikey','bearer'].includes(c.moviepilot.auth))throw Error('不支持的连接方式');
 for(const k of ['reports','records','logs'])c.outputs[k]=localPath(c.outputs[k]);
 for(const k of ['source','target'])if(c.repair[k])c.repair[k]=cloudPath(c.repair[k]);
 if(c.repair.source&&c.repair.target)independent(c.repair.source,c.repair.target);
 c.sourceGapMs=Math.max(45000,Number(c.sourceGapMs)||45000);return c;
}
export function writeConfig(c){validate(c);atomic(path.join(home(),'config.json'),JSON.stringify(c,null,2)+'\n');}
export function publicConfig(c){const r=structuredClone(c);r.cloud.token=r.cloud.token?'[已设置]':'';r.moviepilot.token=r.moviepilot.token?'[已设置]':'';return r;}
// Config snapshots intentionally exclude secrets; executing jobs must retain the same endpoints.
export function snapshot(c){const r=structuredClone(c);delete r.cloud.token;delete r.moviepilot.token;return r;}
export function hydrate(s,c){if(s.cloud.url!==c.cloud.url||s.moviepilot.url!==c.moviepilot.url)throw Error('任务连接地址与当前设置不同，请恢复原连接后继续');return {...s,cloud:{...s.cloud,token:c.cloud.token},moviepilot:{...s.moviepilot,token:c.moviepilot.token}};}
