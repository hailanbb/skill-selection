const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../season-audit.user.js');
const show = C.showInfo('江湖夜雨终似梦 (2025) [tmdbid=303289]');
const row = (name, directory = false) => ({ name, directory });
const video = n => row(`江湖夜雨终似梦 - S01E${String(n).padStart(2,'0')} - 江湖夜雨终似梦.Realm.s.Night.Rain.Dreamlike.S01E${String(n).padStart(2,'0')}.2025.2160p.WEB-DL.H264.AAC-ADWeb.mp4`);

test('目录解析保留中文标题、年份及 TMDB 标识', () => {
  assert.deepEqual(show, { title: '江湖夜雨终似梦', year: '2025', tmdb: '303289' });
  assert.equal(C.seasonNumber('Season 12'), 12);
  assert.equal(C.seasonNumber('Season 0'), null);
  assert.equal(C.seasonNumber('Season 1 extra'), null);
});
test('真实页面样本：22 个视频 + 23 个 NFO，缺第 11、12 集', () => {
  const eps = Array.from({length:24},(_,i)=>i+1).filter(n=>![11,12].includes(n));
  const videos = eps.map(video);
  const rows = [...videos, ...videos.map(r=>row(r.name.replace(/\.mp4$/,'.nfo'))), row('season.nfo')];
  assert.equal(rows.length,45);
  const result = C.auditEpisodes(rows,1,24);
  assert.equal(result.videoCount,22);
  assert.equal(result.current,22);
  assert.deepEqual(result.missing,[11,12]);
  assert.equal(result.integrity,'未完结');
});
test('24 集齐全，仅统计视频；海报、字幕、NFO 不计入', () => {
  const rows = [...Array.from({length:24},(_,i)=>video(i+1)),row('poster.jpg'),row('S01E25.nfo'),row('S01E25.srt')];
  const result = C.auditEpisodes(rows,1,24);
  assert.equal(result.integrity,'齐全'); assert.equal(result.current,24);
});
test('文件数量相等但重复或缺集不能算齐全', () => {
  const r = C.auditEpisodes([video(1),video(1),video(3)],1,3);
  assert.equal(r.videoCount,3); assert.equal(r.current,2);
  assert.deepEqual(r.missing,[2]); assert.equal(r.integrity,'待核实');
});
test('同一文件重复出现相同 S01E01 标记不误判为双集', () => {
  assert.equal(C.episodeFromName(video(1).name,1),1);
});
test('错误季、合并集、冲突标记、纯年份标签均不猜测', () => {
  for (const name of ['show.S02E01.mkv','show.S01E01E02.mkv','show.S01E01-E02.mkv','show.S01E01-02.mkv','show.S01E01.alt.S01E02.mp4','江湖夜雨终似梦.2025.2160p.mp4']) assert.equal(C.episodeFromName(name,1),null,name);
});
test('支持简单中文集号、EP 和纯数字名称', () => {
  assert.equal(C.episodeFromName('某剧 第12集.mp4',1),12);
  assert.equal(C.episodeFromName('某剧.EP12.mp4',1),12);
  assert.equal(C.episodeFromName('012.mkv',1),12);
});
test('越界集号、未知视频、子目录均进入待核实', () => {
  for(const rows of [[video(1),video(25)],[video(1),row('未知.mp4')],[video(1),row('另一个文件夹',true)]]) assert.equal(C.auditEpisodes(rows,1,24).integrity,'待核实');
});
test('总集数未知不当作缺零集或齐全', () => {
  const result=C.auditEpisodes([video(1)],1,null);
  assert.equal(result.integrity,'待核实'); assert.equal(result.missing,null);
});
test('豆瓣标题允许不可见字符，首季必须年份一致', () => {
  const c={title:'江湖夜雨终似梦\u200e (2025)',url:'https://movie.douban.com/subject/37824932/',tv:true};
  assert.equal(C.chooseCandidate([c],show,1),c);
  assert.equal(C.chooseCandidate([{...c,title:'江湖夜雨终似梦 (2024)'}],show,1),null);
  assert.equal(C.chooseCandidate([{...c,tv:false}],show,1),null);
});
test('同名同年有多个豆瓣条目时不选第一个', () => {
  const c={title:'江湖夜雨终似梦 (2025)',url:'https://movie.douban.com/subject/1/',tv:true};
  assert.equal(C.chooseCandidate([c,{...c,url:'https://movie.douban.com/subject/2/'}],show,1),null);
  assert.equal(C.chooseCandidate([c,c],show,1),c);
});
test('台湾剧回归：简繁双标题对应同一剧名，不被误排除', () => {
  const s=C.showInfo('阿荣与阿玉 (2024) [tmdbid=273042]');
  const c={title:'阿荣与阿玉 阿榮與阿玉\u200e (2024)',url:'https://movie.douban.com/subject/37105602/',tv:true};
  assert.equal(C.chooseCandidate([c],s,1,{inspectDetails:true}),c);
  assert.equal(C.candidateMatches(c,s,1),true);
  assert.equal(C.parseTotal('首播: 2024-11-04(中国台湾)\n集数: 60\n'),60);
});
test('台湾剧回归：片名中的空格不影响简繁双标题识别', () => {
  assert.equal(C.sameTitle('欢迎光临 二代咖啡 歡迎光臨 二代咖啡 (2022)','欢迎光临 二代咖啡'),true);
  assert.equal(C.sameTitle('師大公園地下社會','师大公园地下社会'),true);
});
test('标题年份不同仅进入详情核实，首播年份吻合才通过', () => {
  const s=C.showInfo('欢迎光临 二代咖啡 (2025) [tmdbid=205380]');
  const c={title:'欢迎光临 二代咖啡 歡迎光臨 二代咖啡 (2022)',url:'https://movie.douban.com/subject/35840199/',tv:true};
  assert.equal(C.chooseCandidate([c],s,1),null);
  assert.equal(C.chooseCandidate([c],s,1,{inspectDetails:true}),c);
  assert.equal(C.candidateMatches({...c,releaseYears:['2025','2022']},s,1),true);
  assert.equal(C.candidateMatches({...c,releaseYears:['2022']},s,1),false);
  assert.match(C.matchFailure([{...c,releaseYears:['2022']}],s,1,true),/年份/);
});
test('不能用前缀、相似标题或改名续作自动认定为同一剧', () => {
  assert.equal(C.sameTitle('阿荣与阿玉之新生活 阿榮與阿玉之新生活','阿荣与阿玉'),false);
  assert.equal(C.sameTitle('阿荣与阿玉 阿榮的故事','阿荣与阿玉'),false);
  assert.equal(C.sameTitle('何百芮的地狱恋曲','何百芮的地狱毒白'),false);
});
test('忽略搜索年份进入详情时，也不任意选择多个候选', () => {
  const s={title:'某剧',year:'2025'},c={title:'某剧 (2025)',url:'https://movie.douban.com/subject/1/',tv:true};
  assert.equal(C.chooseCandidate([c,{...c,title:'某剧 (2020)',url:'https://movie.douban.com/subject/2/'}],s,1,{inspectDetails:true}),null);
  assert.match(C.matchFailure([c,{...c,url:'https://movie.douban.com/subject/2/'}],s,1),/多个/);
});
test('简繁双标题的后续季仍严格检查季数', () => {
  const s={title:'如果我不曾见过太阳',year:'2025'};
  assert.equal(C.candidateMatches({title:'如果我不曾见过太阳 第二季 如果我不曾見過太陽 第二季 (2025)',tv:true},s,2),true);
  assert.equal(C.candidateMatches({title:'如果我不曾见过太阳 如果我不曾見過太陽 (2025)',tv:true},s,2),false);
});
test('报告区别未查到集数与确定没有缺集，并保留候选标题', () => {
  const csv=C.resultCsv([{missing:null,candidateTitles:['阿荣与阿玉 阿榮與阿玉 (2024)']},{missing:[]}]);
  assert.ok(csv.includes('"未确认"')); assert.ok(csv.includes('"无"'));
  assert.ok(csv.includes('豆瓣候选标题')); assert.ok(csv.includes('阿榮與阿玉'));
});
test('第二季只匹配明确第二季，年份可不同于整剧目录年份', () => {
  const s={title:'某剧',year:'2020',tmdb:'123'};
  assert.equal(C.candidateMatches({title:'某剧 第二季 (2023)',tv:true},s,2),true);
  assert.equal(C.candidateMatches({title:'某剧 (2023)',tv:true},s,2),false);
  assert.equal(C.candidateMatches({title:'某剧 第三季 (2023)',tv:true},s,2),false);
});
test('豆瓣集数字段严格读取，不从片长或评论提取数字', () => {
  assert.equal(C.parseTotal('导演: 张铭座\n集数: 24\n单集片长: 15分钟'),24);
  assert.equal(C.parseTotal('单集片长: 24分钟\n'),null);
  assert.equal(C.parseTotal('集数: 待定\n'),null);
  assert.equal(C.parseTotal('集数: 24 / 30\n'),null);
});
test('豆瓣要求登录时提示人工处理，普通登录链接不误报', () => {
  assert.match(C.doubanAccessProblem({text:'请先登录再查看'}),/手动登录/);
  assert.match(C.doubanAccessProblem({text:'短信登录',hasLoginForm:true}),/手动登录/);
  assert.equal(C.doubanAccessProblem({text:'登录/注册 豆瓣电影 搜索'}),null);
  assert.equal(C.doubanAccessProblem({text:'登录/注册 集数: 24',hasContent:true}),null);
});
test('豆瓣验证码页面要求人工处理，有效内容页不因评论提及验证码而阻断', () => {
  assert.match(C.doubanAccessProblem({text:'访问过于频繁，请输入验证码'}),/人工验证/);
  assert.equal(C.doubanAccessProblem({text:'短评：这段像验证码',hasContent:true}),null);
});
test('绑定链接限制为豆瓣 HTTPS 条目，剔除查询与片段', () => {
  assert.equal(C.validSubjectUrl('https://movie.douban.com/subject/37824932/?x=1#abc'),'https://movie.douban.com/subject/37824932/');
  for (const u of ['javascript:alert(1)','https://evil.com/subject/1/','https://movie.douban.com.evil.com/subject/1/','https://user:pw@movie.douban.com/subject/1/']) assert.equal(C.validSubjectUrl(u),null);
});
test('分页不全、路径不符、重行或空列表均失败', () => {
  const p=C.SOURCE+'/国产剧',r={name:'剧集',path:p+'/剧集'};
  assert.deepEqual(C.validateListing([r],p,1),[r]);
  for (const args of [[[r],p,2],[[r],C.DEST,1],[[r,r],p,2],[[],p,0]]) assert.throws(()=>C.validateListing(...args));
});
test('CSV 正确处理中文、换行、双引号及公式前缀', () => {
  assert.equal(C.csvCell('a"b\nc'),'"a""b\nc"');
  assert.equal(C.csvCell('=1+1'),'"\'=1+1"');
  const csv=C.resultCsv([{category:'国产剧',showName:'江湖夜雨终似梦',missing:[11,12]}]);
  assert.equal(csv.charCodeAt(0),0xfeff);
  assert.ok(csv.includes('11、12')); assert.ok(csv.endsWith('\r\n'));
});
test('交付脚本 UTF-8 无 BOM，仅允许 TMDB API 跨域，无远程代码依赖与云端写操作入口', () => {
  const bytes=fs.readFileSync(path.join(__dirname,'../season-audit.user.js'));
  assert.notEqual(bytes.subarray(0,3).toString('hex'),'efbbbf');
  const source=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  assert.ok(source.startsWith('// ==UserScript=='));
  assert.ok(!/@require|GM_cookie|\bfetch\s*\(/.test(source));
  assert.deepEqual([...source.matchAll(/^\/\/ @connect\s+(.+)$/gm)].map(m=>m[1]),['api.themoviedb.org']);
  assert.ok(!/querySelector\([^\n]*(?:移动|删除|重命名)/.test(source));
});
