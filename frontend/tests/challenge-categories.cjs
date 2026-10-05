const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

const sourcePath = path.resolve(__dirname, '../src/lib/challengeCategories.ts');
const compiled = ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const fixtureModule = new Module(sourcePath, module);
fixtureModule._compile(compiled, sourcePath);
const { normalizeChallengeCategory, isValidChallengeCategory, challengeCategoryOptions } = fixtureModule.exports;

assert.equal(normalizeChallengeCategory('  redes   y defensa '), 'REDES Y DEFENSA');
assert.equal(isValidChallengeCategory('REDES Y DEFENSA'), true);
for (const invalid of ['X', '   ', 'WEB<script>', 'A'.repeat(49), 'A\nB']) {
  assert.equal(isValidChallengeCategory(invalid), false, invalid);
}
assert.deepEqual(challengeCategoryOptions(['MISC', 'WEB'], ['Redes y defensa', 'WEB'], 'MISC'),
  ['MISC', 'REDES Y DEFENSA', 'WEB']);
console.log('PASS configurable challenge categories');
