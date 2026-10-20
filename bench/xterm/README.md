# The terminal in xterm.js

VS Code's terminal is xterm.js. A frame that holds in a fake tty or a plain pty can still stack
there, because xterm re-wraps rows when the column count changes. This runs ds-next (or any
program) under node-pty, feeds it into headless xterm.js, types, resizes, and prints the screen.

```sh
cd bench/xterm && npm install
chmod +x node_modules/node-pty/prebuilds/*/spawn-helper   # npm drops the exec bit
node run.js 90 45 /ne RESIZE:88x45 RESIZE:86x45 RESIZE:95x45     # one box, or ghosts?
node run.js 150 45 /new ENTER RESIZE:88x45                       # the form through a resize
CMD=$(which cortex) CWD=$HOME/Developer/canon BOOT=9000 node run.js 90 45 hello RESIZE:89x45
```

The last line of the output counts `New session` rules: one is right, more is the stacking.
`LOG=out.log` keeps every byte and every reply the terminal sent back, for reading what a
program does on resize (that is how Cortex Code's clear-and-reprint was found).
