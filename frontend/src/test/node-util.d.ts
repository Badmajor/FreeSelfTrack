// The data-router tests use Node's controller with Node's native Request,
// while jsdom supplies a different AbortSignal implementation.
declare module "node:util" {
  export function transferableAbortController(): AbortController;
}
