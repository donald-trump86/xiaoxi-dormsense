// Execute the actual TUI Banner and native markup parser without a terminal or server.
const assert = require('node:assert/strict')
const ts = require('typescript')

function compile(source) {
  return ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React, jsxFactory: 'h' }
  }).outputText.replace(/^export /gm, '')
}

const parser = new Function(`${compile(globalThis.__bannerSource)}; return {logo, artWidth};`)()
const ast = ts.createSourceFile('branding.tsx', globalThis.__brandingSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const banner = ast.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === 'Banner')
assert(banner, 'the real Banner component must exist')
let columns = 80
const h = (type, props, ...children) => ({ type, props: { ...props, children } })
const Banner = new Function('h', 'Box', 'Text', 'ArtLines', 'useStdout', 'logo', 'artWidth',
  `${compile(banner.getText(ast))}; return Banner;`)(h, 'Box', 'Text', 'ArtLines', () => ({ stdout: { columns } }), parser.logo, parser.artWidth)
const markup = Array.from({ length: 7 }, (_, row) => `[#E2B27E]${row === 1 ? ' ' : '██'.repeat(31)}[/]`).join('\n')
const theme = { color: { primary: '#E2B27E' }, brand: { name: 'xiaoxi' }, bannerLogo: markup }

for (const width of [64, 80, 120]) {
  columns = width
  const child = Banner({ t: theme }).props.children[0]
  assert.equal(child.type, 'ArtLines')
  assert.equal(child.props.lines.length, 7)
  assert.equal(parser.artWidth(child.props.lines), 62)
  assert(child.props.lines.every(([color, text]) => color === '#E2B27E' && !text.includes('[/]')))
}
for (const width of [20, 63]) {
  columns = width
  const child = Banner({ t: theme }).props.children[0]
  assert.equal(child.type, 'Text')
  assert.deepEqual(child.props.children, ['xiaoxi'])
}
columns = 120
assert.equal(Banner({ maxWidth: 63, t: theme }).props.children[0].type, 'Text')
assert.equal(Banner({ maxWidth: 64, t: theme }).props.children[0].type, 'ArtLines')
assert.deepEqual(Banner({ t: { ...theme, bannerLogo: '' } }).props.children[0].props.lines, [['', 'xiaoxi']])
console.log('PASS: TUI pixel banner at 64/80/120 columns, narrow/maxWidth fallback, markup and plain-name fallback')
