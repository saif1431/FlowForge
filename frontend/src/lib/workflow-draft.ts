import { createStore } from "zustand/vanilla";

// One store per mounted workflow: never share an unsaved draft across tenants.
// JSON is the lossless graph representation shared by visual and advanced editors.
export function createWorkflowDraft() {
  return createStore<{
    editor: string;
    savedText: string;
    setEditor: (editor: string) => void;
    setSavedText: (savedText: string) => void;
  }>((set) => ({
    editor: "", savedText: "",
    setEditor: (editor) => set({ editor }),
    setSavedText: (savedText) => set({ savedText }),
  }));
}
