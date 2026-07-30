// Constantes injectées au build par Vite (voir `define` dans vite.config.ts).
// Elles sont remplacées littéralement dans le bundle : aucune lecture à l'exécution.
declare const __APP_VERSION__: string; // numéro lisible, issu du fichier /VERSION
declare const __GIT_SHA__: string; // commit exact à partir duquel le front a été construit
declare const __BUILD_DATE__: string; // date du build, au format ISO
