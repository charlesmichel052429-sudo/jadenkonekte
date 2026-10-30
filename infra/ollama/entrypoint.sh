#!/bin/sh
# Démarre Ollama puis télécharge le modèle s'il n'est pas déjà dans le volume (une seule fois, ~1 Go).
set -eu
ollama serve &
SERVEUR=$!
until ollama list > /dev/null 2>&1; do sleep 1; done
if ! ollama show "$OLLAMA_MODELE" > /dev/null 2>&1; then
  echo "Téléchargement du modèle $OLLAMA_MODELE…"
  ollama pull "$OLLAMA_MODELE"
fi
echo "Modèle $OLLAMA_MODELE prêt."
wait $SERVEUR
