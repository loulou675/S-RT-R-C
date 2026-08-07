/**
 * Training mode is a build-time switch. Keep it disabled for client-facing
 * builds; enable it only in a local or private field-test build.
 */
export const trainingModeEnabled = import.meta.env.VITE_TRAINING_MODE === 'true'
