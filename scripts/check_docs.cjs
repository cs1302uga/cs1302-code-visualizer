// Lint all repository-owned Markdown and check local file destinations.
const { execFileSync, spawnSync } = require('node:child_process');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const frontend = path.join(root, 'cs1302_code_visualizer/frontend');
const requireFrontend = createRequire(path.join(frontend, 'package.json'));
const MarkdownIt = requireFrontend('markdown-it');
const parser = new MarkdownIt({ html: true });
const excluded = new Set(['node_modules', '.venv', 'dist', 'build', 'wheels']);
const files = [...new Set(execFileSync('git', [
  'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '*.md',
], { cwd: root, encoding: 'utf8' }).split('\0').filter(Boolean))]
  .filter(file => !file.split('/').some(part => excluded.has(part)))
  .filter(file => existsSync(path.join(root, file))).sort();
if (!files.length) throw new Error('No repository Markdown files found');
const result = spawnSync(path.join(frontend, 'node_modules/.bin/markdownlint'), [
  '--config', '.markdownlint.yaml', ...(process.argv.includes('--fix') ? ['--fix'] : []),
  ...files,
], { cwd: root, stdio: 'inherit' });
if (result.error) throw result.error;
let failures = 0;
function check(file, target) {
  if (!target || /^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(target)) return;
  const destination = target.split(/[?#]/)[0];
  if (!destination) return;
  let decoded;
  try { decoded = decodeURIComponent(destination); } catch { decoded = destination; }
  const resolved = decoded.startsWith('/')
    ? path.join(root, decoded) : path.resolve(root, path.dirname(file), decoded);
  if (!existsSync(resolved)) {
    console.error(`${file}: missing local destination: ${target}`);
    failures++;
  }
}
function visit(file, tokens) {
  for (const token of tokens) {
    if (token.type === 'link_open') check(file, token.attrGet('href'));
    if (token.type === 'image') check(file, token.attrGet('src'));
    if (token.type === 'html_inline' || token.type === 'html_block') {
      for (const match of token.content.matchAll(/\b(?:href|src)\s*=\s*["']([^"']+)["']/gi)) {
        check(file, match[1]);
      }
    }
    if (token.children) visit(file, token.children);
  }
}
for (const file of files) visit(file, parser.parse(readFileSync(path.join(root, file), 'utf8'), {}));
console.log(`Checked ${files.length} Markdown files; ${failures} missing local destinations.`);
process.exitCode = result.status || (failures ? 1 : 0);
