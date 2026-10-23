// Load pinned upstream pure business factories; browser controllers are never executed.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'../vendor/workflow');
const read=n=>fs.readFileSync(path.join(root,n+'.js'),'utf8');
const source=read('season-inspect');
function section(a,b){if(source.split(a).length!==2||source.split(b).length!==2)throw Error('Upstream boundary changed');return source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));}
const convert=require('../vendor/opencc.cjs').Converter({from:'tw',to:'cn'});
function factory(n){return vm.runInThisContext(read(n).replaceAll('/* build:repair-state */ null',read('repair-state')),{filename:n+'.js'});}
const C=vm.runInThisContext('(function(toSimplified){'+section('  const MEDIA =','  async function preferTmdb(')+section('  function parseTotal(','  function csvCell(')+section('  function modifiedTime(','  function sortModified(')+';return {MEDIA,norm,parent,base,mapKey,showInfo,titleIdentity,candidateMatches,chooseCandidate,matchFailure,episodeFromName,auditEpisodes,validSubjectUrl,parseTotal,parseTmdbSeason,parseDoubanBroadcast,doubanAccessProblem,validateListing,createListingSettler,modifiedTime,cleanTitleText};})')(convert);
const Cleanup=factory('cleanup-core')(C),Versions=factory('version-download')(Cleanup),Broadcast=factory('broadcast-audit')();
const Download=factory('download-core')(C,Versions,Broadcast),RepairState=factory('repair-state')();
module.exports={C,Cleanup,Versions,Download,RepairState,Repair:factory('transfer-repair')(Download,C,RepairState,Versions),archive:settings=>factory('archive-core')(C,settings)};
