const Fastify=require('fastify'),path=require('node:path');
const Store=require('./store.cjs'),{CloudDrive,MoviePilot,TMDB}=require('./clients.cjs'),{Workflow}=require('./workflow.cjs');
function build(workflow,{apiKey=process.env.BACKEND_API_KEY,writes=process.env.ALLOW_REMOTE_WRITES==='true'}={}){
 const app=Fastify({logger:false,bodyLimit:10*1024*1024});let running=null;
 app.addHook('onRequest',async(req,reply)=>{if(apiKey&&req.headers['x-api-key']!==apiKey)return reply.code(401).send({error:'Unauthorized'});});
 app.setErrorHandler((e,req,reply)=>reply.code(400).send({error:e.message}));
 const work=fn=>async(req,reply)=>{if(running)return reply.code(409).send({error:'A job is running'});const id=require('node:crypto').randomUUID();running={id,pause:false};workflow.store.set('job:'+id,{id,state:'running'});const checkpoint=()=>{if(running?.pause)throw Error('Paused at checkpoint; inspect journal before continuing');};Promise.resolve().then(()=>fn(req,checkpoint)).then(result=>workflow.store.set('job:'+id,{id,state:'finished',result})).catch(e=>workflow.store.set('job:'+id,{id,state:'stopped',error:e.message})).finally(()=>{running=null;});return reply.code(202).send({jobId:id});};
 app.get('/health',async()=>({status:'ok',writesEnabled:writes}));
 app.get('/seasons',async()=>workflow.store.all('row:'));
 app.get('/jobs/:id',async req=>workflow.store.get('job:'+req.params.id));
 app.post('/jobs/:id/pause',async req=>{if(running?.id!==req.params.id)throw Error('Job not running');running.pause=true;return {pauseRequested:true};});
 app.post('/scan',work(()=>workflow.scan()));
 app.post('/seasons/:id/inspect',work(req=>workflow.inspect(req.params.id,req.body?.doubanId)));
 app.post('/plans',work(async req=>workflow.publicPlan(await workflow.plan(req.body.kind,req.body.seasonIds,req.body))));
 app.get('/plans/:id',async req=>{const p=workflow.store.get('plan:'+req.params.id);if(!p)throw Error('Unknown plan');return workflow.publicPlan(p);});
 app.post('/plans/:id/execute',work((req,checkpoint)=>{if(!writes)throw Error('Remote writes disabled; set ALLOW_REMOTE_WRITES=true after reviewing the plan');if(req.body?.confirm!==true)throw Error('Explicit confirm:true required');return workflow.execute(req.params.id,req.body.hash,checkpoint);}));
 app.post('/plans/:id/reconcile',work(req=>workflow.reconcile(req.params.id)));
 const reports=require('./reports.cjs');
 app.get('/reports.xlsx',async(req,reply)=>reply.header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet').send(reports.freshReport(workflow)));
 app.post('/reports/import',work(req=>{if(!req.body?.base64)throw Error('base64 workbook required');return reports.importReport(workflow,Buffer.from(req.body.base64,'base64'));}));
 app.get('/reports/:id/xlsx',async(req,reply)=>reply.header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet').header('Content-Disposition','attachment; filename="workflow.xlsx"').send(reports.exportReport(workflow,req.params.id,req.query.mode||'download')));
 app.get('/reports',async()=>({schema:1,exportedAt:new Date().toISOString(),seasons:workflow.store.all('row:'),plans:workflow.store.all('plan:').map(p=>workflow.publicPlan(p)),jobs:workflow.store.all('job:')}));
 return app;
}
if(require.main===module){const required=['CD_ORIGIN','CD_TOKEN','MP_ORIGIN','MP_TOKEN','TMDB_API_KEY','SOURCE_ROOT','ARCHIVE_ROOT'];for(const k of required)if(!process.env[k])throw Error('Missing environment variable '+k);const host=process.env.HOST||'127.0.0.1';if(host!=='127.0.0.1'&&!process.env.BACKEND_API_KEY)throw Error('BACKEND_API_KEY required for network binding');const store=new Store(path.resolve(process.env.DATA_DIR||'data','workflow.sqlite'));const cloud=new CloudDrive(process.env.CD_ORIGIN,process.env.CD_TOKEN);const workflow=new Workflow({store,cloud,mp:new MoviePilot(process.env.MP_ORIGIN,process.env.MP_TOKEN,process.env.MP_AUTH_MODE||'apikey'),tmdb:new TMDB(process.env.TMDB_API_KEY,process.env.TMDB_LANGUAGE||'zh-CN'),source:process.env.SOURCE_ROOT,destination:process.env.ARCHIVE_ROOT,repairSource:process.env.MP_REPAIR_SOURCE,repairTarget:process.env.MP_REPAIR_TARGET});const app=build(workflow);app.addHook('onClose',async()=>{cloud.close();store.close();});app.listen({host,port:Number(process.env.PORT||8080)}).then(()=>console.log('TV workflow listening on '+host+':'+(process.env.PORT||8080))).catch(e=>{console.error(e.message);process.exitCode=1;});for(const sig of ['SIGINT','SIGTERM'])process.on(sig,()=>app.close());}
module.exports={build};
