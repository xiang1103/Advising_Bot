// Kills whatever is listening on the given port so `next dev` can bind to it.
// Runs as the `predev` hook; never fails the build — if it can't free the port,
// `next dev` will say so itself.
import { execFileSync } from "node:child_process";

const port = process.argv[2] ?? "3000";

function listeners() {
  try {
    return execFileSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"], {
      encoding: "utf8",
    })
      .split("\n")
      .map((line) => Number(line.trim()))
      .filter((pid) => Number.isInteger(pid) && pid > 0 && pid !== process.pid);
  } catch {
    // lsof exits 1 when nothing matches, and ENOENT if it isn't installed.
    return [];
  }
}

const pids = listeners();
if (pids.length === 0) {
  process.exit(0);
}

for (const pid of pids) {
  try {
    process.kill(pid, "SIGTERM");
    console.log(`free-port: sent SIGTERM to ${pid} holding port ${port}`);
  } catch {
    // Already gone, or not ours to kill.
  }
}

// Give them a moment, then escalate to anything still holding the port.
const deadline = Date.now() + 2000;
while (Date.now() < deadline && listeners().length > 0) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100);
}

for (const pid of listeners()) {
  try {
    process.kill(pid, "SIGKILL");
    console.log(`free-port: sent SIGKILL to ${pid} holding port ${port}`);
  } catch {
    // Already gone.
  }
}
