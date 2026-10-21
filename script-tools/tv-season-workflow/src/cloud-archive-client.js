/* CloudDrive2 归档页面适配器：只开放已配置源/目标树内的读取和整剧/单季移动。
 * 复用只读列表代码，不引入第三阶段的删除入口或豆瓣后台页。
 * 目标必须是现有分类或同剧目录；遇到冲突或额外确认窗口停止，不选择覆盖、合并或复制。
 */
(function createCloudArchiveClient(C,options) {
  'use strict';
  const {checkpoint:check}=options;
  const SOURCE=options.source||'/115/Library_incs/nas/电视剧',DEST=options.destination||'/115/Library_incs/nas.finish/电视剧';
  const {parent,createListingSettler}=C;
  /* build:cloud-listing */
  const cleanText=e=>(e?.textContent||'').replace(/[\uE000-\uF8FF]/g,'').trim();
  const dialogs=()=>[...document.querySelectorAll('[role="dialog"]')].filter(visible);
  const selected=()=>[...document.querySelectorAll('table.file-list tr.file-row.selected')];
  function cancel(){for(const d of dialogs())if(cleanText(d.querySelector('.modal-title'))==='移动/复制到...')[...d.querySelectorAll('button')].find(b=>cleanText(b)==='取消')?.click();}
  async function moveShow(plan,expectedRows,entry) {
    let submitted=false;
    function unchanged() {
      const key=r=>JSON.stringify([r.path,r.name,!!r.directory,r.modified,r.size]),expected=new Map(expectedRows.map(r=>[r.path,key(r)])),current=readRows();
      if(currentPath()!==parent(plan.source)||breadcrumbPath()!==parent(plan.source)||current.length!==expectedRows.length||current.some(r=>expected.get(r.path)!==key(r))||readCount()!==current.length||document.querySelector('select.page-size-select')?.value!=='all')throw Error('移动确认前源列表或分页发生变化');
      requireConnected();checkpoint();
    }
    try {
      const seasonMove=plan.kind==='season'&&parent(plan.source)===plan.showSource&&parent(plan.showSource)===SOURCE+'/'+plan.category&&plan.showTarget===DEST+'/'+plan.category+'/'+C.base(plan.showSource)&&/^Season\s+[0-9]+$/i.test(entry?.name||'')&&plan.target===plan.showTarget+'/'+entry?.name;
      const showMove=plan.kind!=='season'&&parent(plan.source)===SOURCE+'/'+plan.category&&plan.target===DEST+'/'+plan.category+'/'+entry?.name;
      if(!entry?.directory||entry.path!==plan.source||(!seasonMove&&!showMove)||!allowed(plan.source)||!allowed(plan.target))throw Error('拒绝移动计划外目录');
      if(dialogs().length)throw Error('请先关闭页面已有的对话框');unchanged();
      for(const row of selected())row.querySelector('.file-icon')?.dispatchEvent(new MouseEvent('click',{bubbles:true,ctrlKey:true}));
      await waitFor(()=>!selected().length,'旧文件选择未清除');
      const row=[...document.querySelectorAll('table.file-list tr.file-row[data-path]')].find(r=>r.getAttribute('data-path')===plan.source);
      if(!row?.classList.contains('directory'))throw Error('源目录已变化');row.querySelector('.file-name-ellipsis')?.click();
      const menu=await waitFor(()=>[...document.querySelectorAll('[role="menu"]')].find(visible),'目录菜单未出现');
      const action=[...menu.querySelectorAll('[role="menuitem"],button')].find(e=>cleanText(e)==='移动/复制到...');if(!action)throw Error('找不到移动入口');action.click();
      const dialog=await waitFor(()=>dialogs().find(d=>cleanText(d.querySelector('.modal-title'))==='移动/复制到...'),'移动窗口未出现');
      dialog.querySelector('.folder-breadcrumb-bar .breadcrumb-edit-btn')?.click();
      const input=await waitFor(()=>dialog.querySelector('input.breadcrumb-path-input'),'移动路径输入框未出现');
      setInput(input,parent(plan.target));input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));
      let last='',stableSince=0;
      await waitFor(()=>{
        if(cleanText(dialog.querySelector('.selected-path-display span'))!==parent(plan.target)){stableSince=0;return false;}
        if(dialog.querySelector('.fa-spinner')||/加载中|Loading/i.test(cleanText(dialog.querySelector('.folder-list')))){stableSince=0;return false;}
        const list=dialog.querySelector('.folder-list');if(!list||/失败|错误|error|failed/i.test(cleanText(list)))throw Error('目标分类列表加载失败');
        if([...dialog.querySelectorAll('.folder-list-item:not(.up-folder)')].some(e=>[...e.querySelectorAll('span')].some(s=>cleanText(s).normalize('NFC').toLowerCase()===entry.name.normalize('NFC').toLowerCase()||seasonMove&&Number(/^Season\s+(\d+)$/i.exec(cleanText(s))?.[1])===Number(/^Season\s+(\d+)$/i.exec(entry.name)?.[1]))))throw Error('目标已出现同名目录，取消移动');
        // 路径文字可能先于异步列表更新，必须等目标清单稳定后才允许提交。
        const fingerprint=cleanText(list);if(!stableSince||last!==fingerprint){last=fingerprint;stableSince=Date.now();return false;}
        return Date.now()-stableSince>=1800;
      },'目标分类尚未确认加载，未发出移动');
      unchanged();
      if(selected().length!==1||selected()[0].getAttribute('data-path')!==plan.source||dialogs().length!==1)throw Error('移动选择范围或对话框发生变化');
      if([...dialog.querySelectorAll('.folder-select-warning')].some(visible))throw Error('目标目录有警告，停止移动');
      const button=dialog.querySelector('button[aria-label="移动"]');if(!button||button.disabled)throw Error('移动按钮不可用');
      // 面板已经列出并确认整剧清单。这里只触发一次移动；不点击任何后续冲突处理选项。
      finishing++;submitted=true;
      try {
        button.click();await waitFor(()=>{
          if(dialogs().some(d=>d!==dialog))throw Error('出现额外确认/冲突窗口，请人工核实；脚本不会覆盖或合并');
          return !visible(dialog);
        },'移动请求尚未结束，请核实结果');
      }finally{finishing--;}
    }catch(e){if(!submitted){cancel();e.notSubmitted=true;}throw e;}
  }
  return {listing,moveShow,currentPath,readRows,requireConnected};
})
