#!/bin/sh
# Crée les comptes MQTT à partir des variables d'environnement, puis lance Mosquitto.
# Les fichiers sont copiés dans /mosquitto/data avec des droits restreints, exigés par Mosquitto.
set -eu

PW=/mosquitto/data/passwd
rm -f "$PW"
touch "$PW"
chmod 0700 "$PW"
mosquitto_passwd -b "$PW" app        "$MQTT_APP_MOT_DE_PASSE"
mosquitto_passwd -b "$PW" simulateur "$MQTT_SIMULATEUR_MOT_DE_PASSE"
if [ -n "${MQTT_CAPTEUR_P1_MOT_DE_PASSE:-}" ]; then
  mosquitto_passwd -b "$PW" capteur-p1 "$MQTT_CAPTEUR_P1_MOT_DE_PASSE"
fi

cp /mosquitto/config/acl /mosquitto/data/acl
chmod 0700 /mosquitto/data/acl
chown mosquitto:mosquitto "$PW" /mosquitto/data/acl

exec mosquitto -c /mosquitto/config/mosquitto.conf
