// 每次资源查询保留MoviePilot默认范围，再显式追加这两个站点；不修改服务端站点设置。
const required=[{name:'天空',aliases:['天空','天空pt','skyey','skyey2']},{name:'观众',aliases:['观众','观众pt','audiences']}];
const normalized=s=>String(s||'').normalize('NFKC').replace(/\s+/g,'').toLowerCase();
const empty=r=>r?.success===false&&/^(未搜索到任何资源|没有搜索到任何资源|No resources found)[。.!！]?$/.test(String(r.message||''));
function resources(result){if(empty(result))return [];if(result?.success!==true||!Array.isArray(result.data))throw Error('站点搜索未完整成功，不能按部分结果提交下载');return result.data;}
function key(c){const t=c.torrent_info||{};return JSON.stringify([String(t.site??t.site_name??''),String(t.title||''),Number(t.size)||0,String(t.pubdate||'')]);}
export function withExtraSites(api,{progress=()=>{}}={}){
 let sitesPromise,selection,lastFailure='';
 async function resolve(){
  if(!sitesPromise)sitesPromise=(async()=>{
   const raw=await api.get('site/',{timeout:30000});
   if(!Array.isArray(raw))throw Error('MoviePilot站点列表格式不支持，无法追加天空和观众');
   // 不保留或记录站点Cookie、账号等字段。
   const list=raw.map(s=>({id:Number(s.id),name:String(s.name||''),active:s.is_active}));
   selection=required.map(want=>{
    const matches=list.filter(s=>want.aliases.includes(normalized(s.name)));
    if(matches.length!==1||!Number.isSafeInteger(matches[0]?.id)||matches[0].id<=0)throw Error('站点“'+want.name+'”未找到唯一有效配置，请先在MoviePilot添加或核对名称');
    if(matches[0].active===false||matches[0].active===0)throw Error('站点“'+want.name+'”未启用，停止本轮资源选择');
    return {id:matches[0].id,name:want.name};
   });
   if(new Set(selection.map(s=>s.id)).size!==required.length)throw Error('追加站点ID重复');
   progress('搜索范围：MoviePilot默认站点 + '+selection.map(s=>s.name+'（ID '+s.id+'）').join(' + '));
   return selection;
  })();
  return sitesPromise;
 }
 return {defaults:api.defaults,post:(...args)=>api.post(...args),selection:()=>selection?structuredClone(selection):[],failure:()=>lastFailure,
  get:async(route,options={})=>{
   if(!/^search\/(?:media\/|title$)/.test(route))return api.get(route,options);
   lastFailure='';try{
    const sites=await resolve(),params={...options.params};delete params.sites;
    const defaults=resources(await api.get(route,{...options,params}));
    const additional=resources(await api.get(route,{...options,params:{...params,sites:sites.map(s=>s.id).join(',')}}));
    const seen=new Set(),data=[...defaults,...additional].filter(c=>{const k=key(c);if(seen.has(k))return false;seen.add(k);return true;});
    return {success:true,data};
   }catch(e){lastFailure=String(e.message||'追加站点查询失败');progress(lastFailure);throw e;}
  }
 };
}
