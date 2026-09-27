// Revisión de código local/remoto conocido, sin escribir en Instant ni usar red.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import vm from 'node:vm';
const root='/Users/atiemppoia/codex/SICETAC-INSTANT';
const require=createRequire(`${root}/package.json`);
const React=require('react'), {renderToStaticMarkup}=require('react-dom/server');
const files=['app/page.jsx','app/api/route/route.js','app/lib/sicetac-options.js'];
const local=Object.fromEntries(files.map(f=>[f,readFileSync(`${root}/${f}`,'utf8')]));
const remote=Object.fromEntries(files.map(f=>[f,execFileSync('git',['-C',root,'show',`origin/main:${f}`],{encoding:'utf8'})]));
const results=[];
function check(version,name,fn){try{fn();results.push({version,name,status:'pass'});}catch(e){results.push({version,name,status:'gap',detail:e.message});}}

function pageContext(source) {
  const start=source.indexOf('  async function onSubmit(e) {');
  const end=source.indexOf('\n  return (',start);
  assert(start>0&&end>start,'Cambió Page: revisar extractor');
  const requests=[];
  const ctx=vm.createContext({origen:'Cartagena',destino:'Cúcuta',vehiculo:'C3S3',carroceria:'Portacontenedores',modoViaje:'CARGADO',tipoContenedor:'CARGADO',viajeRedondo:true,rutasSeleccionadas:{ida:'ruta-anterior-ida',regreso:'ruta-anterior-regreso'},
    setLoading:()=>{},setResult:()=>{},setDetail:()=>{},setDetailError:()=>{},setError:value=>{ctx.error=value;},
    setOrigen:value=>{ctx.origen=value;},setTipoContenedor:value=>{ctx.tipoContenedor=value;},
    fetch:async(_url,options)=>{requests.push(JSON.parse(options.body));return{ok:true,json:async()=>({ok:true})};},
  });
  vm.runInContext(source.slice(start,end),ctx);
  function change(id,value) {
    const re=new RegExp(`id="${id}"[\\s\\S]*?onChange=\\{\\(e\\) => ([^\\n]+)\\}`);
    const match=source.match(re);assert(match,`Cambió handler ${id}`);
    vm.runInContext(`(e)=>${match[1]}`,ctx)({target:{value}});
  }
  return{ctx,requests,change,submit:()=>ctx.onSubmit({preventDefault(){}})};
}

for(const [version,source] of [['working_tree',local],['origin_main',remote]]) {
  const old=pageContext(source['app/page.jsx']); old.change('origen','Bogotá');await old.submit();
  check(version,'Cambiar origen debe descartar RUTASID de la consulta anterior',()=>{
    assert.equal(old.requests[0].rutasid_ida,null);
    assert.equal(old.requests[0].rutasid_regreso,null);
  });
  const conflict=pageContext(source['app/page.jsx']);conflict.change('tipo-contenedor','VACIO');await conflict.submit();
  check(version,'El formulario no debe enviar ida vacía dentro del redondo cargado',()=>{
    assert(!conflict.requests.some(p=>p.viaje_redondo&&p.tipo_contenedor==='VACIO'),'El formulario envía viaje_redondo=true y tipo_contenedor=VACIO');
  });
  const errorCase=pageContext(source['app/page.jsx']);
  errorCase.ctx.fetch=async()=>({ok:false,json:async()=>({detail:[{msg:'Error de validación',type:'value_error'}]})});
  await errorCase.submit();
  check(version,'El error estructurado del backend debe poder renderizarse',()=>{
    assert.doesNotThrow(()=>renderToStaticMarkup(React.createElement('div',null,errorCase.ctx.error)));
  });

  const sent=[];
  const ctx=vm.createContext({Request,Response,AbortSignal,URL,process:{env:{}},
    fetch:async(_url,options)=>{sent.push(JSON.parse(options.body));return Response.json({origen:'Cartagena',destino:'Cúcuta',totales:{H4:1}});},
  });
  const handler=source['app/api/route/route.js'].replace(/^import[^\n]+\n/,'').replace('export async function POST','async function POST');
  vm.runInContext(source['app/lib/sicetac-options.js'].replace(/\bexport /g,'')+'\n'+handler,ctx);
  const request=payload=>new Request('https://example.invalid/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const base={origen:'Cartagena',destino:'Cúcuta',vehiculo:'C3S3',carroceria:'Portacontenedores',modo_viaje:'CARGADO',tipo_contenedor:'CARGADO',viaje_redondo:true,tipo_contenedor_regreso:'VACIO'};
  await ctx.POST(request(base));
  check(version,'Viaje combinado válido conserva ida cargada y regreso contenedor vacío',()=>{
    assert.equal(sent[0].modo_viaje,'CARGADO'); assert.equal(sent[0].tipo_contenedor,'CARGADO');
    assert.equal(sent[0].tipo_contenedor_regreso,'VACIO');assert.equal(sent[0].viaje_redondo,true);
  });
  await ctx.POST(request({...base,viaje_redondo:false,tipo_contenedor:'VACIO',tipo_contenedor_regreso:null}));
  check(version,'Devolución independiente conserva vehículo cargado y contenedor vacío',()=>{
    assert.equal(sent[1].modo_viaje,'CARGADO');assert.equal(sent[1].tipo_contenedor,'VACIO');assert.equal(sent[1].viaje_redondo,undefined);
  });
  const invalid=await ctx.POST(request({...base,modo_viaje:'VACIO'}));
  check(version,'El proxy rechaza viaje redondo con vehículo vacío',()=>assert.equal(invalid.status,400));
}
console.log(JSON.stringify({status:'review_only',requests_to_live_services:0,writes_to_instant:0,
  local_head:execFileSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),
  remote_ref:execFileSync('git',['-C',root,'rev-parse','origin/main'],{encoding:'utf8'}).trim(),
  hashes:Object.fromEntries(files.map(f=>[f,createHash('sha256').update(local[f]).digest('hex')])),
  pass:results.filter(x=>x.status==='pass').length,gap:results.filter(x=>x.status==='gap').length,results},null,2));
