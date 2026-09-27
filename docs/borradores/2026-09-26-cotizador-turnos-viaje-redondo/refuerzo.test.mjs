// Se ejecuta desde una copia temporal del plugin; nunca abre la bandeja real.
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { openDatabase, upsertTenant, recordInbox, enqueueJobs, nextJob, attachResult } from '../src/store.js';
import { createTools } from '../src/index.js';

function setup(t) {
  const dir=mkdtempSync(join(tmpdir(),'cotizador-refuerzo-test-'));
  const dbPath=join(dir,'queue.sqlite'), db=openDatabase(dbPath);
  t.after(()=>{ db.close(); rmSync(dir,{recursive:true,force:true}); });
  const tenants=[['AT-COT-001','at_cot_001'],['ateam','bruno_at']].map(([tenant_id,agent_id])=>({tenant_id,agent_id,channel:'whatsapp',group_id:`test-${tenant_id}`,specialist_session_key:'agent:atica-cotizador-api:main'}));
  for(const tenant of tenants) upsertTenant(db,{...tenant,conversation_id:tenant.group_id});
  let n=0;
  function enqueue(jobs,tenantId='AT-COT-001',raw='Cotizar contenedor') {
    const inbox=recordInbox(db,{tenant_id:tenantId,message_id:`synthetic-${++n}`,raw_text:raw}).inbox;
    return enqueueJobs(db,{tenantId,inboxId:inbox.inbox_id,jobs});
  }
  return {db,enqueue,config:{dbPath,tenants}};
}
const simple={origin:'Cartagena',destination:'Cúcuta',service:'contenedor',configuration:'C2S3'};
const round={...simple,origin_return:'Cúcuta',destination_return:'Buenaventura',viaje_redondo_con_retorno_vacio:true,contenedor_vacio:false};
function close(db,job,extra={}) {
  return attachResult(db,{tenantId:job.tenant_id,jobId:job.job_id,status:'answered',request_id:job.request_id,json_response:{request_id:job.request_id,status:'ok'},visible_reply:'Resultado sintético',...extra});
}

for(const [name,payload] of [
  ['ida vacía dentro de redondo',{...round,contenedor_vacio:true}],
  ['dos trayectos con bandera false',{...round,viaje_redondo_con_retorno_vacio:false}],
  ['regreso incompleto',{...round,destination_return:null}],
  ['redondo sin extremos',{...simple,viaje_redondo_con_retorno_vacio:true}],
  ['bandera textual',{...round,contenedor_vacio:'false'}],
  ['servicio incompatible',{...round,service:'carga general'}],
]) test(`rechaza ${name} sin insertar parcialmente`,t=>{
  const {db,enqueue}=setup(t);
  assert.throws(()=>enqueue([simple,payload]));
  assert.equal(db.prepare('SELECT COUNT(*) n FROM jobs').get().n,0);
});

test('retorno a otro puerto conserva extremos, configuración y nombre literal',t=>{
  const {enqueue}=setup(t);
  const job=enqueue([{...round,destination:'Puerto Antioquia',origin_return:null}]).jobs[0];
  assert.equal(job.interpreted.destination,'Puerto Antioquia');
  assert.equal(job.interpreted.origin_return,'Puerto Antioquia');
  assert.equal(job.interpreted.destination_return,'Buenaventura');
  assert.equal(job.interpreted.configuration,'C2S3');
});

test('devolución independiente sigue siendo un único trayecto con contenedor vacío',t=>{
  const {enqueue}=setup(t);
  const job=enqueue([{...simple,contenedor_vacio:true,viaje_redondo_con_retorno_vacio:false}]).jobs[0];
  assert.equal(job.interpreted.origin_return,null);
  assert.equal(job.interpreted.destination_return,null);
  assert.equal(job.interpreted.contenedor_vacio,true);
});

test('escenarios 15/30 t avanzan serialmente sin cruzar tenants o inbox',t=>{
  const {db,enqueue}=setup(t);
  const jobs=enqueue([15,30].map(weight_total=>({...round,weight_total,weight_unit:'t'}))).jobs;
  enqueue([simple]); enqueue([simple],'ateam');
  // Fuerza empate para comprobar FIFO según orden de inserción.
  db.prepare("UPDATE jobs SET created_at='2026-09-26T00:00:00Z'").run();
  const a=nextJob(db,{tenantId:'AT-COT-001'});
  const waiting=nextJob(db,{tenantId:'AT-COT-001'});
  assert.equal(a.job.job_id,jobs[0].job_id); assert.equal(a.dispatch_allowed,true);
  assert.equal(waiting.dispatch_allowed,false); assert.equal(waiting.action,'wait');
  const other=nextJob(db,{tenantId:'ateam'}); assert.equal(other.dispatch_allowed,true);
  assert.notEqual(other.job.request_id,a.job.request_id);
  close(db,a.job);
  const b=nextJob(db,{tenantId:'AT-COT-001',inboxId:a.job.inbox_id});
  assert.equal(b.job.job_id,jobs[1].job_id); close(db,b.job);
  const idle=nextJob(db,{tenantId:'AT-COT-001',inboxId:a.job.inbox_id});
  assert.equal(idle.action,'idle'); assert.equal(idle.dispatch_allowed,false);
});

test('IDs del argumento, sobre y canonical deben coincidir; rechazo no libera el turno',t=>{
  const {db,enqueue}=setup(t); const job=enqueue([simple]).jobs[0];
  nextJob(db,{tenantId:job.tenant_id});
  for(const bad of [
    {request_id:'incorrecto'},
    {json_response:{request_id:'incorrecto'}},
    {json_response:{request_id:job.request_id,canonical:{request_id:'incorrecto'}}},
    {request_id:null},
    {json_response:{status:'ok'}},
  ]) assert.throws(()=>close(db,job,bad),/request_id/);
  assert.equal(nextJob(db,{tenantId:job.tenant_id}).already_in_flight,true);
  assert.equal(db.prepare('SELECT request_id FROM jobs WHERE job_id=?').get(job.job_id).request_id,job.request_id);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM events WHERE action='job_attached'").get().n,0);
  close(db,job); assert.equal(nextJob(db,{tenantId:job.tenant_id}).job,null);
});

test('cierre repetido es idempotente y no admite cambiar respuesta ni estado',t=>{
  const {db,enqueue}=setup(t); const job=enqueue([simple]).jobs[0];
  const first=close(db,job), replay=close(db,job);
  assert.equal(first.idempotent,false); assert.equal(replay.idempotent,true);
  assert.equal(replay.job.completed_at,first.job.completed_at);
  assert.throws(()=>close(db,job,{visible_reply:'Otro valor'}),/immutable/);
  assert.throws(()=>close(db,job,{status:'failed'}),/immutable/);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM events WHERE action='job_attached'").get().n,1);
});

for(const gatewayOwned of [false,true]) test(`attach duplicado no repite entrega, gatewayOwned=${gatewayOwned}`,async t=>{
  const {db,enqueue,config}=setup(t); const job=enqueue([simple]).jobs[0]; let sent=0;
  const ctx={agentId:'at_cot_001',messageChannel:'whatsapp',deliveryContext:{channel:'whatsapp',to:'test-AT-COT-001'},
    ...(gatewayOwned?{}:{delivery:{send:async()=>{ sent++;return{messageId:'synthetic-send'}; }}})};
  const tools=createTools(ctx,config), attach=tools.find(x=>x.name==='bandeja_attach');
  const params={job_id:job.job_id,status:'answered',request_id:job.request_id,json_response:{request_id:job.request_id,status:'ok'},visible_reply:'Prueba local'};
  const call=async p=>JSON.parse((await attach.execute('test',p)).content[0].text);
  const bad=await call({...params,json_response:{request_id:'otro-tenant'}});
  assert.equal(bad.ok,false); assert.equal(sent,0);
  const first=await call(params), second=await call(params);
  assert.equal(first.delivery.status,gatewayOwned?'deferred':'sent');
  assert.equal(second.delivery.status,'already_attached');
  assert.equal(second.delivery.reply_required,false);
  assert.equal(sent,gatewayOwned?0:1);
});
