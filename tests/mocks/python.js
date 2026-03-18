/**
 * Mocking utility for Python backend calls.
 * Enables deterministic testing without a live environment.
 */
export function mockPythonResponse(module, funct, result, exitCode = 0) {
  return {
    stdout: JSON.stringify(result),
    stderr: "",
    code: exitCode
  };
}

/**
 * Mocks the child_process.spawn implementation for bridge tests.
 */
export class MockSpawn {
  constructor(response, delay = 10) {
    this.response = response;
    this.delay = delay;
    this.stdout = { on: (event, cb) => {
      if (event === 'data') setTimeout(() => cb(this.response.stdout), this.delay);
    }};
    this.stderr = { on: (event, cb) => {
      if (event === 'data' && this.response.stderr) setTimeout(() => cb(this.response.stderr), this.delay);
    }};
  }

  on(event, cb) {
    if (event === 'close') setTimeout(() => cb(this.response.code), this.delay + 5);
    if (event === 'error' && this.response.code === -1) setTimeout(() => cb(new Error("Spawn error")), this.delay);
  }

  kill(signal) {
    this.killed = true;
    this.signal = signal;
  }
}
