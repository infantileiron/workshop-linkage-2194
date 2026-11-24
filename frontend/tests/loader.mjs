// ESM loader：补全无扩展名的相对导入，并把 api/session 模块重定向到测试 mock。
import {dirname, resolve as pathResolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const HERE = dirname(new URL(import.meta.url).pathname);
const FRONTEND = pathResolve(HERE, '..');
const MOCK = {
  [pathResolve(FRONTEND, 'src/api/workshop.js')]: pathResolve(HERE, 'mock-api.mjs'),
  [pathResolve(FRONTEND, 'src/stores/session.js')]: pathResolve(HERE, 'mock-session.mjs'),
};

export async function resolve(specifier, context, nextResolve) {
  if ((specifier.startsWith('./') || specifier.startsWith('../')) && context.parentURL) {
    const path = new URL(specifier, context.parentURL).pathname;
    if (MOCK[path]) return nextResolve(pathToFileURL(MOCK[path]).href, context);
    if (!/\.[a-z]+$/.test(path)) return nextResolve(pathToFileURL(path + '.js').href, context);
  }
  return nextResolve(specifier, context);
}
