import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const sdk = createRequire('/Users/atiemppoia/.npm-global/lib/node_modules/openclaw/package.json');
const plugin = createRequire('/Users/atiemppoia/codex/openclaw/plugins/cotizador-bandeja/package.json');
export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith('openclaw/')) return nextResolve(pathToFileURL(sdk.resolve(specifier)).href, context);
  if (specifier === 'typebox') return nextResolve(pathToFileURL(plugin.resolve(specifier)).href, context);
  return nextResolve(specifier, context);
}
