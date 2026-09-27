// Diagnóstico aislado: solo lee código instalado; HTTP simulado y SQLite temporal.
// No importa el plugin ni activa su registro, auditoría o mensajería.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import vm from "node:vm";

const plugins = "/Users/atiemppoia/codex/openclaw/plugins";
const storePath = process.env.COTIZADOR_STORE || `${plugins}/cotizador-bandeja/src/store.js`;
const adapterPath = `${plugins}/atica-cotizador-readonly/dist/index.js`;
const store = await import(pathToFileURL(storePath));
const root = mkdtempSync(join(tmpdir(), "cotizador-draft-"));
const results = [];

function check(name, fn) {
  try { fn(); results.push({ name, status: "pass" }); }
  catch (error) { results.push({ name, status: "gap", detail: error.message }); }
}

function queue() {
  const db = store.openDatabase(join(root, `queue-${results.length}.sqlite`));
  for (const [tenant, agent] of [["AT-COT-001", "at_cot_001"], ["ateam", "bruno_at"]]) {
    store.upsertTenant(db, { tenant_id: tenant, agent_id: agent, channel: "whatsapp",
      conversation_id: `test-${tenant}`, specialist_session_key: "agent:atica-cotizador-api:main" });
  }
  return db;
}

function enqueue(db, jobs, raw = "Cotizar viaje redondo con devolución") {
  const inbox = store.recordInbox(db, { tenant_id: "AT-COT-001", message_id: "draft-only",
    raw_text: raw, actor: "local-test" }).inbox;
  return store.enqueueJobs(db, { tenantId: "AT-COT-001", inboxId: inbox.inbox_id,
    jobs, actor: "local-test" });
}

const round = { origin: "Cartagena", destination: "Cúcuta", origin_return: "Cúcuta",
  destination_return: "Cartagena", service: "contenedor", container_size_ft: 40,
  weight_total: 29, weight_unit: "t", weight_includes_tare: true, configuration: "C2S3",
  viaje_redondo_con_retorno_vacio: true, contenedor_vacio: false, horas_logisticas: 4 };

try {
  let db = queue();
  try {
    check("Una solicitud conserva ida y devolución en un solo job", () => {
      const out = enqueue(db, [round]);
      assert.equal(out.created_count, 1);
      assert.equal(out.jobs[0].interpreted.viaje_redondo_con_retorno_vacio, true);
      assert.equal(out.jobs[0].interpreted.destination_return, "Cartagena");
    });
    check("El turno activo se conserva y el otro tenant queda aislado", () => {
      const first = store.nextJob(db, { tenantId: "AT-COT-001", actor: "local-test" });
      const repeat = store.nextJob(db, { tenantId: "AT-COT-001", actor: "local-test" });
      const other = store.nextJob(db, { tenantId: "ateam", actor: "local-test" });
      assert.equal(repeat.already_in_flight, true);
      assert.equal(repeat.job.job_id, first.job.job_id);
      assert.equal(other.job, null);
    });
    check("El cierre debe rechazar un request_id distinto al asignado", () => {
      const active = store.nextJob(db, { tenantId: "AT-COT-001", actor: "local-test" }).job;
      assert.throws(() => store.attachResult(db, { tenantId: "AT-COT-001", jobId: active.job_id,
        request_id: "DRAFT-WRONG-ID", json_response: { request_id: "DRAFT-WRONG-ID", status: "ok" },
        status: "answered", actor: "local-test" }));
    });
  } finally { db.close(); }

  db = queue();
  try {
    check("La cola debe rechazar ida cargada marcada a la vez como contenedor vacío", () => {
      assert.throws(() => enqueue(db, [{ ...round, contenedor_vacio: true }]));
    });
  } finally { db.close(); }

  db = queue();
  try {
    check("La cola debe rechazar dos trayectos con viaje redondo desactivado", () => {
      assert.throws(() => enqueue(db, [{ ...round, viaje_redondo_con_retorno_vacio: false }]));
    });
  } finally { db.close(); }

  // Ejecutar únicamente la construcción de solicitud del adaptador compilado.
  // La respuesta, la auditoría y el transporte se sustituyen por dobles locales.
  const source = readFileSync(adapterPath, "utf8");
  function section(start, end) {
    const a = source.indexOf(start), b = source.indexOf(end, a + start.length);
    assert(a >= 0 && b > a, "Cambió el archivo instalado; revisar el extractor antes de ejecutar");
    return source.slice(a, b);
  }
  const sent = [];
  const context = vm.createContext({
    URL, AbortSignal, Date, PREQUOTE_API_BASE_URL: "",
    audit: async () => {}, compactHostedResult: () => ({}),
    asRecord: value => value || {},
    fetch: async (_url, options) => {
      sent.push(JSON.parse(options.body));
      return { ok: true, status: 200, text: async () => '{"ok":true,"data":{}}' };
    },
  });
  vm.runInContext(section("function hostedPrequoteUrl(", "function asRecord(") + "\n" +
    section("async function hostedPrequoteCall(", "async function ateamRouteLookup("), context);
  const params = { request_id: "DRAFT-ROUNDTRIP", origen: "Cartagena", destino: "Cúcuta",
    origen_regreso: "Cúcuta", destino_regreso: "Cartagena", tipo_servicio: "contenedor",
    tamano_contenedor: 40, configuracion_sicetac: "C2S3", peso_total_incluida_tara: 29000,
    unidad_peso: "kg", viaje_redondo_con_retorno_vacio: true, salida: "canonica" };
  const config = { prequoteApiBaseUrl: "https://example.invalid", prequoteApiKey: "synthetic-test-only" };
  const result = await context.hostedPrequoteCall(params, config);
  check("El adaptador envía una llamada con ida CARGADO y regreso VACIO", () => {
    assert.equal(result.status, "ok"); assert.equal(sent.length, 1);
    assert.equal(sent[0].viaje_redondo, true);
    assert.equal(sent[0].tipo_contenedor, "CARGADO");
    assert.equal(sent[0].tipo_contenedor_regreso, "VACIO");
    assert.equal(sent[0].destino_regreso, "Cartagena");
    assert.equal(sent[0].requested_configuration, "C2S3");
  });
  await context.hostedPrequoteCall({ ...params, viaje_redondo_con_retorno_vacio: false,
    contenedor_vacio: true, origen_regreso: undefined, destino_regreso: undefined }, config);
  check("La devolución independiente usa tipo_contenedor VACIO sin modo vehicular VACIO", () => {
    assert.equal(sent[1].tipo_contenedor, "VACIO");
    assert.equal(sent[1].modo_viaje, undefined); // API existente: valor por defecto CARGADO.
    assert.equal(sent[1].viaje_redondo, undefined);
  });
  await context.hostedPrequoteCall({ ...params, destino: "Puerto Antioquia" }, config);
  check("El adaptador conserva el nombre para la resolución central", () => {
    assert.equal(sent[2].destino, "Puerto Antioquia");
  });
  console.log(JSON.stringify({ status: "draft_diagnostic", live_requests: 0, live_writes: 0,
    hashes: Object.fromEntries([storePath, adapterPath].map(path => [path,
      createHash("sha256").update(readFileSync(path)).digest("hex")])),
    summary: { pass: results.filter(r => r.status === "pass").length,
      gap: results.filter(r => r.status === "gap").length }, results }, null, 2));
} finally { rmSync(root, { recursive: true, force: true }); }
