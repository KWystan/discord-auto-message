// Fresh-clone setup from the repository root.
const { spawnSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const rootDir = path.join(__dirname, '..')
const clientDir = path.join(rootDir, 'client')
const serverDir = path.join(rootDir, 'server')
const venvDir = path.join(serverDir, 'venv')
const venvPython = path.join(
  venvDir,
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status ?? 1)
}

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'
run(npm, ['install'], clientDir)

if (!fs.existsSync(venvPython)) {
  const python = process.platform === 'win32' ? 'py' : 'python3'
  const args = process.platform === 'win32'
    ? ['-3', '-m', 'venv', venvDir]
    : ['-m', 'venv', venvDir]
  run(python, args, rootDir)
}

run(venvPython, ['-m', 'pip', 'install', '-r', 'requirements.txt'], serverDir)
console.log('\nSetup complete. Copy server/.env.example to server/.env, then run npm run start.')
