import {test} from 'node:test';
import assert from 'node:assert/strict';
import {withExtraSites} from '../lib/search-sites.js';
const r=(site,title='剧.S01E01')=>({torrent_info:{site,site_name:'站'+site,title,size:100,pubdate:'2026-10-26'}});
test('默认站点与天空/观众两次查询合并，保留默认结果并去重',async()=>{
 const calls=[],events=[],api={defaults:{baseURL:'/api/v1/'},get:async(route,opts)=>{calls.push([route,opts]);if(route==='site/')return [{id:2,name:'天空',cookie:'PRIVATE'},{id:3,name:'观众'}];return {success:true,data:opts.params.sites?[r(2),r(3),r(1)]:[r(1)]};},post:async()=>{}};
 const a=withExtraSites(api,{progress:t=>events.push(t)}),out=await a.get('search/media/tmdb%3A1',{params:{season:'1',_ts:1}});
 assert.deepEqual(out.data.map(c=>c.torrent_info.site),[1,2,3]);assert.equal(calls[1][1].params.sites,undefined);assert.equal(calls[2][1].params.sites,'2,3');assert.equal(calls[2][1].params.season,'1');
 await a.get('search/title',{params:{page:1,keyword:'剧'}});assert.equal(calls.filter(c=>c[0]==='site/').length,1);assert.ok(!JSON.stringify([events,a.selection()]).includes('PRIVATE'));
});
test('追加站点缺失、重名、停用或站点API不完整时不降级为默认搜索',async()=>{
 for(const sites of [[{id:1,name:'天空'}],[{id:1,name:'天空'},{id:2,name:'天空'},{id:3,name:'观众'}],[{id:1,name:'天空',is_active:false},{id:2,name:'观众'}],{success:true,data:[]}]){
  let searched=0;const api={get:async route=>route==='site/'?sites:(searched++,{success:true,data:[]}),post:()=>{}};
  await assert.rejects(()=>withExtraSites(api).get('search/title',{params:{}}));assert.equal(searched,0);
 }
});
test('任一搜索返回未知失败时不按部分资源继续；明确无结果可合并为空',async()=>{
 const sites=[{id:1,name:'Skyey'},{id:2,name:'Audiences'}];let bad=true;
 const api={get:async(route,opts)=>route==='site/'?sites:opts.params.sites?(bad?{success:false,message:'timeout'}:{success:false,message:'未搜索到任何资源'}):{success:true,data:[r(7)]},post:()=>{}};
 const a=withExtraSites(api);await assert.rejects(()=>a.get('search/title',{params:{}}),/未完整成功/);bad=false;assert.equal((await a.get('search/title',{params:{}})).data.length,1);
});
