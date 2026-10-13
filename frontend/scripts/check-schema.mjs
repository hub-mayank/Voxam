// Fails when src/api/schema.ts is not what `npm run gen:api` would write from ../docs/openapi.json.
// A stale schema means the typed client no longer matches the frozen contract.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const dir = mkdtempSync(join(tmpdir(), 'voxam-schema-'))
const out = join(dir, 'schema.ts')
try {
  execFileSync('npx', ['openapi-typescript', '../docs/openapi.json', '-o', out], { stdio: 'ignore' })
  if (readFileSync(out, 'utf8') !== readFileSync('src/api/schema.ts', 'utf8')) {
    console.error('src/api/schema.ts is out of date: run `npm run gen:api` and commit it (docs/openapi.json changed).')
    process.exit(1)
  }
  console.log('schema.ts matches docs/openapi.json')
} finally {
  rmSync(dir, { recursive: true, force: true })
}
