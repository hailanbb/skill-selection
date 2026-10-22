// 完整安装包中的真实列表适配器；虚拟时钟覆盖加载、错误和缓存残留，不访问云盘。
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const I=require('../season-inspect.user.js'),dir=I.SOURCE+'/日本剧集/测试剧 (2025)/Season 1';
async function read(stage,options={}){
  let clock=0,refreshes=0,healthReads=0;
  const visible={getClientRects:()=>[{}]},text=textContent=>({textContent}),name='测试.S01E01.mkv';
  const row={getAttribute:()=>dir+'/'+name,classList:{contains:()=>false},querySelector:s=>({'.file-name-text':text(name),'.file-size':text('1 GB'),'.file-modified':text(clock<500?'旧列表时间':'刷新后时间')}[s])};
  const document={querySelector:s=>{
    if(s.includes('health-indicator')){healthReads++;return null;}
    return {'.files-breadcrumb-bar .breadcrumb-edit-btn':{},'button.toolbar-refresh-btn':{click(){refreshes++;}},'select.page-size-select':{options:[{value:'all'}],value:'all'},'.file-list-status':text((options.empty?0:options.partial?2:1)+' items')}[s]||null;
  },querySelectorAll:s=>{
    if(s==='.files-breadcrumb-bar .breadcrumb-item:not(.breadcrumb-root)')return dir.split('/').slice(1).map(text);
    if(s==='table.file-list tr.file-row[data-path]')return options.empty?[]:[row];
    if(s==='.file-list-scroll-area .loading-bar')return refreshes&&(clock<500||options.stuck)?[visible]:[];
    if(s==='.files-load-error')return options.failed&&clock>=500?[{...visible,textContent:'读取文件失败'}]:[];
    if(s==='table.file-list .empty-state .empty-content p')return options.empty&&!options.unconfirmedEmpty&&clock>=500?[{...visible,textContent:'此文件夹为空'}]:[];
    return [];
  }};
  const box={exports:{}},context={module:box,URL,document,location:{href:'https://clouddrive.example/?page=files&path='+encodeURIComponent(dir)},Date:class extends Date{static now(){return clock;}},setTimeout(fn,ms){clock+=ms;queueMicrotask(fn);}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../season-'+stage+'.user.js'),'utf8'),context);
  const C=box.exports,client=C.createClient(C,{checkpoint(){},get(){},put(){},del(){},message(){},ready:()=>true});
  try{return {rows:await client.listing(dir),refreshes,healthReads,clock};}catch(error){return {error,refreshes,healthReads,clock};}
}
test('第三/第四脚本不读取 connected 标记，等待实际刷新完成后返回稳定列表',async()=>{
  for(const stage of ['review','archive']){const r=await read(stage);assert.equal(r.error,undefined);assert.equal(r.refreshes,1);assert.equal(r.healthReads,0);assert.equal(r.rows.length,1);assert.equal(r.rows[0].modified,'刷新后时间');assert.ok(r.clock>=2300);}
});
test('实际加载失败即使残留旧行也暂停，不接受缓存行；超时和分页不全同样暂停',async()=>{
  for(const stage of ['review','archive'])for(const options of [{failed:true},{stuck:true},{partial:true}]){const r=await read(stage,options);assert.equal(r.error?.name,'Pause');assert.equal(r.rows,undefined);assert.equal(r.healthReads,0);assert.match(r.error.message,/加载失败|未读全/);}
});
test('确认空目录才返回0；空白但没有空目录提示不能当作0',async()=>{
  for(const stage of ['review','archive']){const ok=await read(stage,{empty:true});assert.equal(ok.error,undefined);assert.equal(ok.rows.length,0);const bad=await read(stage,{empty:true,unconfirmedEmpty:true});assert.equal(bad.error.name,'Pause');assert.equal(bad.rows,undefined);}
});
