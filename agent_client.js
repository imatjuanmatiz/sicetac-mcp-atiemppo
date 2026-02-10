const API_URL = process.env.SICETAC_API_URL || "https://sicetac-api-mcp.onrender.com";

async function consultarResumen(origen, destino) {
  const res = await fetch(`${API_URL}/consulta`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origen, destino }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function consultarDetalle(origen, destino) {
  const res = await fetch(`${API_URL}/consulta`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origen, destino, resumen: false }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function main() {
  const [origen, destino] = process.argv.slice(2);
  if (!origen || !destino) {
    console.error("Uso: node agent_client.js <origen> <destino>");
    process.exit(1);
  }
  const resumen = await consultarResumen(origen, destino);
  console.log(JSON.stringify(resumen, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
