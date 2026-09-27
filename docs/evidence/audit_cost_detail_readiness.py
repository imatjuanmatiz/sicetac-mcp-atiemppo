"""Auditoría local reproducible. Lee capturas y evidencia; no conecta ni publica."""
from __future__ import annotations

import ast
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modelo_sicetac import calcular_modelo_sicetac_extendido
from modelo_sicetac_vacio import calcular_modelo_sicetac_extendido_vacio
from peajes_totalizador import normalize_toll_configuration

OUT = ROOT / "docs/evidence"
LOCAL = Path('/Users/atiemppoia/codex/SICETAC-SIMULADOR-LOCAL')
capture_path = LOCAL / 'data/sicetac_captura_simulaciones_20260901.json'
builder_path = LOCAL / 'scripts/build_snapshot_20260901.py'
snapshot_path = LOCAL / 'data/sicetac_modelo_local_202609.duckdb'
capture = json.loads(capture_path.read_text())
sources = json.loads((OUT / 'cost-detail-readiness-sources-2026-09-22.json').read_text())
tree = ast.parse(builder_path.read_text())
meta = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'META' for t in n.targets))
db = sources['supabase']
params = {p['tipo_vehiculo']: p for p in db['parametros_actuales']}
route = db['ruta_93']
distances = {f'km_{k}': route[f'km_{k}'] for k in ['plano','ondulado','montanoso','urbano','despavimentado']}
tolls = {normalize_toll_configuration(t['configuracion']): t['total_peajes'] for t in sources['tolls']['peajes_ruta93']}
fixed_current = {(f['tipo_vehiculo'], f['tipo_carroceria']): f for f in db['costos_fijos_actuales']}

def money(value):
    return float(str(value).replace('$','').replace(',','').strip())

cases = []
asof_cases = []
for group, mode in [('loaded','CARGADO'), ('empty','VACIO')]:
    for item in capture[group]:
        label = item['label']
        vehicle = meta[label][0]
        source = item['data']
        assert item.get('ok') is True
        assert label in source['route'] and mode in source['route'] and '20260901' in source['route']
        body = 'GRANEL SOLIDO - VOLCO' if vehicle.startswith('V') else 'GENERAL'
        fixed_value = money(source['fixedSubtotal'][0])
        p = dict(params[vehicle])
        p.update({'TIPO_VEHICULO':vehicle,'MES':p['mes_codigo'],'HORAS_HABILES_MES':p['horas_habiles_mes'], 'VALOR COMBUSTIBLE GALÓN ACPM':p['valor_combustible_galon_acpm'], 'COSTOS VARIABLES':p['costos_variables'],'COSTOS VARIABLES VACIO':p['costos_variables_vacio']})
        fixed = pd.DataFrame([{'TIPO_VEHICULO':vehicle,'MES':202609,'TIPO_CARROCERIA':body,'COSTO FIJO':fixed_value}])
        vehicles = pd.DataFrame([{'TIPO_VEHICULO':vehicle,'EJES_CONFIGURACION':p['ejes_configuracion']}])
        model = calcular_modelo_sicetac_extendido if mode == 'CARGADO' else calcular_modelo_sicetac_extendido_vacio
        result = model(origen='Bogotá',destino='Barranquilla',configuracion=vehicle,serie=202609,distancias=distances,valor_peaje_manual=0,matriz_parametros=pd.DataFrame([p]),matriz_costos_fijos=fixed,matriz_vehicular=vehicles,rutas_df=pd.DataFrame(),peajes_df=pd.DataFrame(),carroceria_especial=body,horas_logisticas=4,valor_peaje_override=tolls[normalize_toll_configuration(vehicle)])
        total = result.get('total_viaje',result.get('total_viaje_vacio'))
        components = sum(result[k] for k in ['costo_fijo','combustible','peajes','mantenimiento','imprevistos','otros_costos'])
        gallons = sum(t['gal'] for t in result['detalle_via'].values())
        assert math.isfinite(total) and total > 0
        assert abs(round(components,2)-total) < 0.011
        assert abs(round(gallons*p['valor_combustible_galon_acpm'],2)-result['combustible']) < 0.011
        assert abs(sum(t['km'] for t in result['detalle_via'].values())-route['total_km']) < 0.011
        current = fixed_current.get((vehicle,body))
        cases.append({'vehicle':vehicle,'mode':mode,'body':body,'fixed_source_month':202609,'fixed_source_capture':str(capture_path),'fixed_monthly_captured':fixed_value,'fixed_monthly_database':current['costo_fijo'] if current else None,'fixed_month_database':current['mes_codigo'] if current else None,'same_as_database':bool(current and abs(current['costo_fijo']-fixed_value)<0.011),'total_model':total,'gallons':gallons,'components_reconcile':True,'fuel_reconciles':True,'result':result})
        # Regla confirmada por el usuario: el costo fijo sigue vigente hasta reemplazo.
        # Adaptación en memoria para evaluar el motor sin cambiar la fecha en la fuente.
        assert current and current['mes_codigo'] <= 202609
        effective_fixed = pd.DataFrame([{'TIPO_VEHICULO':vehicle,'MES':202609,'MES_FUENTE':current['mes_codigo'],'TIPO_CARROCERIA':body,'COSTO FIJO':current['costo_fijo']}])
        effective_result = model(origen='Bogotá',destino='Barranquilla',configuracion=vehicle,serie=202609,distancias=distances,valor_peaje_manual=0,matriz_parametros=pd.DataFrame([p]),matriz_costos_fijos=effective_fixed,matriz_vehicular=vehicles,rutas_df=pd.DataFrame(),peajes_df=pd.DataFrame(),carroceria_especial=body,horas_logisticas=4,valor_peaje_override=tolls[normalize_toll_configuration(vehicle)])
        effective_total = effective_result.get('total_viaje',effective_result.get('total_viaje_vacio'))
        effective_components = sum(effective_result[k] for k in ['costo_fijo','combustible','peajes','mantenimiento','imprevistos','otros_costos'])
        assert math.isfinite(effective_total) and effective_total>0
        assert abs(round(effective_components,2)-effective_total)<0.011
        assert effective_result['detalle_via']==result['detalle_via']
        assert effective_result['combustible']==result['combustible']
        asof_cases.append({'vehicle':vehicle,'mode':mode,'body':body,'periodo_calculo':202609,'mes_origen_costo_fijo':current['mes_codigo'],'costo_fijo_vigente':current['costo_fijo'],'selection_rule':'ultimo costo aplicable no posterior al periodo solicitado, vigente hasta reemplazo; confirmado por el usuario','total_model':effective_total,'components_reconcile':True,'fuel_reconciles':True,'result':effective_result})

summary = {
    'checked_at':datetime.now(timezone.utc).isoformat(),
    'scope':'Controlled local execution of unchanged model with current Supabase parameters and toll totals plus September fixed costs read directly from dated local capture. Not deployed or promoted; no published quote total used as an input or acceptance target.',
    'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [capture_path,builder_path,snapshot_path]},
    'source_capture_cut':capture['cut'],
    'cases_count':len(cases),'passed':len(cases),
    'different_fixed_values':[{'vehicle':c['vehicle'],'mode':c['mode'],'body':c['body'],'captured':c['fixed_monthly_captured'],'database':c['fixed_monthly_database']} for c in cases if not c['same_as_database']],
    'cases':cases,
}
(OUT/'cost-detail-readiness-model-2026-09-22.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['cases','source_hashes']},ensure_ascii=False,indent=2))
print('C3S3 cargado:', json.dumps(next(c for c in cases if c['vehicle']=='C3S3' and c['mode']=='CARGADO')['result'],ensure_ascii=False))
asof_summary = {'checked_at':datetime.now(timezone.utc).isoformat(),'source':'Supabase read-only snapshot in cost-detail-readiness-sources-2026-09-22.json','policy_authority':'User clarification in current conversation: fixed costs remain valid because they have not changed','method':'Existing model; fixed-cost applicability adapted only in memory, keeping original source month in evidence','scope':'Route 93, 13 vehicle configurations, loaded and empty; GENERAL or VOLCO as applicable. This verifies computability and arithmetic, not all routes/body types or production delivery. Empty dump-truck fixed-cost differences against local captures remain a source-context review item.','cases_count':len(asof_cases),'passed':len(asof_cases),'cases':asof_cases}
(OUT/'cost-detail-readiness-asof-2026-09-22.json').write_text(json.dumps(asof_summary,ensure_ascii=False,indent=2)+'\n')
print('Vigencia hasta reemplazo:',len(asof_cases),'casos calculados con costos de Supabase y fecha original conservada.')
