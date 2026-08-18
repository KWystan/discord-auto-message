// Run the frontend lint and backend test suites from the repository root.
const { spawnSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const rootDir = path.join(__dirname, '..')
const serverDir = path.join(rootDir, 'server')
const venvPython = path.join(
  serverDir,
  'venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const python = fs.existsSync(venvPython) ? venvPython : 'python'

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status ?? 1)
}

run(npm, ['--prefix', 'client', 'run', 'lint'], rootDir)
run(python, ['server/test_engine.py'], rootDir)
run(python, ['server/test_auth.py'], rootDir)
console.log('\nAll checks passed.')
