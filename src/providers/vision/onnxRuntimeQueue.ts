let runtimeTail: Promise<void> = Promise.resolve()

/**
 * ONNX Runtime Web's WASM backend is not re-entrant in every browser build.
 * Keep all model executions serial, including component detection and warm-up.
 */
export function runOnnxExclusive<T>(operation: () => Promise<T>): Promise<T> {
  const result = runtimeTail.then(operation, operation)
  runtimeTail = result.then(
    () => undefined,
    () => undefined,
  )
  return result
}
