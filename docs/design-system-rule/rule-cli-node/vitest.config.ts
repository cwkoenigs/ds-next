import {defineConfig} from 'vitest/config';

// The live tests wait for a frame (until(), 10 s at most); a test may take that long on a loaded machine.
export default defineConfig({test: {testTimeout: 20_000}});
