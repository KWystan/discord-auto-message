// Cross-platform Flask launcher for `npm run api`.
// Uses the server/venv interpreter when it exists (Windows: Scripts/, others: bin/),
// otherwise falls back to `python` on PATH (e.g. an activated venv).
const { spawn } = require('node:child_process')
const path = require('node:path')
const fs = require('node:fs')

const serverDir = path.join(__dirname, '..', 'server')
const venvPython = path.join(
  serverDir,
  'venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
)

const python = fs.existsSync(venvPython) ? venvPython : 'python'
const child = spawn(python, ['api.py'], { cwd: serverDir, stdio: 'inherit' })
child.on('exit', (code) => process.exit(code ?? 0))
