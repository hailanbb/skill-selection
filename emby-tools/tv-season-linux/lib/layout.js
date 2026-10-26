import path from 'node:path';
import {fileURLToPath} from 'node:url';

// 程序自己的配置、数据与产物使用同一个根；Node运行时不属于本程序数据。
// TVFLOW_ROOT仅供隔离开发测试；正式命令与服务固定使用安装位置。
export function layout(env=process.env){
 const root=path.resolve(env.TVFLOW_ROOT||fileURLToPath(new URL('..',import.meta.url)));
 const data=path.join(root,'data');
 const outputs=Object.fromEntries(['reports','records','logs'].map(k=>[k,path.join(root,k)]));
 return {root,data,outputs,config:path.join(root,'config/config.json'),daemonLog:path.join(outputs.logs,'daemon-start.log')};
}
export const inside=(file,root)=>{const p=path.relative(root,file);return !p||!p.startsWith('..'+path.sep)&&p!=='..'&&!path.isAbsolute(p);};
