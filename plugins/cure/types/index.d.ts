export type CureBand = { isDispatcher: boolean }

declare module 'claude-code' {
  interface PluginState {
    cure: { isDispatcher: boolean }
  }
}
