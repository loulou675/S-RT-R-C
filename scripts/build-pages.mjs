import { build } from 'vite'

await build({
  build: {
    outDir: 'docs',
    emptyOutDir: true,
  },
})
