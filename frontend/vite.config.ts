import { defineConfig } from "vite";

// Duas páginas: a página inicial do campus (index.html) e a ferramenta de medição de GPS (medicao.html).
// Caminhos relativos à raiz do projeto (a pasta frontend/).
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        principal: "index.html",
        medicao: "medicao.html",
      },
    },
  },
});
